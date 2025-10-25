import os
import asyncio
import sqlite3
import logging
import random
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import hbold

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN not found!")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация БД
def init_db():
    conn = sqlite3.connect('games.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_stats (
            user_id INTEGER,
            chat_id INTEGER,
            game_type TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id, game_type)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Менеджер активных игр
class GameManager:
    def __init__(self):
        self.active_games = {}
    
    def create_game(self, game_type, chat_id, player1_id, player2_id, player1_name, player2_name):
        game_id = f"{game_type}_{chat_id}_{player1_id}_{player2_id}_{int(time.time())}"
        
        if game_type == "russian_roulette":
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'alive': True, 'turn': True},
                    player2_id: {'name': player2_name, 'alive': True, 'turn': False}
                },
                'revolver': [False] * 6,
                'current_chamber': 0,
                'created_at': datetime.now()
            }
            # Заряжаем 1 патрон в случайную камору
            bullet_chamber = random.randint(0, 5)
            self.active_games[game_id]['revolver'][bullet_chamber] = True
            
        elif game_type == "dice_battle":
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'score': 0, 'rolls_left': 3},
                    player2_id: {'name': player2_name, 'score': 0, 'rolls_left': 3}
                },
                'current_player': player1_id,
                'created_at': datetime.now()
            }
            
        elif game_type == "number_guess":
            target_number = random.randint(1, 100)
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'attempts': 0},
                    player2_id: {'name': player2_name, 'attempts': 0}
                },
                'target_number': target_number,
                'current_player': player1_id,
                'created_at': datetime.now()
            }
            
        elif game_type == "tic_tac_toe":
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'symbol': '❌'},
                    player2_id: {'name': player2_name, 'symbol': '⭕'}
                },
                'board': ['⬜'] * 9,
                'current_player': player1_id,
                'created_at': datetime.now()
            }
            
        elif game_type == "quick_math":
            num1, num2 = random.randint(1, 20), random.randint(1, 20)
            operations = ['+', '-', '*']
            operation = random.choice(operations)
            
            if operation == '+':
                answer = num1 + num2
            elif operation == '-':
                answer = num1 - num2
            else:
                answer = num1 * num2
                
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'score': 0},
                    player2_id: {'name': player2_name, 'score': 0}
                },
                'problem': f"{num1} {operation} {num2}",
                'answer': answer,
                'current_player': player1_id,
                'created_at': datetime.now()
            }
            
        elif game_type == "coin_flip":
            self.active_games[game_id] = {
                'type': game_type,
                'chat_id': chat_id,
                'players': {
                    player1_id: {'name': player1_name, 'choice': None},
                    player2_id: {'name': player2_name, 'choice': None}
                },
                'result': None,
                'created_at': datetime.now()
            }
        
        # Автоудаление игры через 10 минут
        asyncio.create_task(self.remove_game_after_timeout(game_id, 600))
        return game_id
    
    def get_game(self, game_id):
        return self.active_games.get(game_id)
    
    def remove_game(self, game_id):
        if game_id in self.active_games:
            del self.active_games[game_id]
    
    async def remove_game_after_timeout(self, game_id, timeout):
        await asyncio.sleep(timeout)
        self.remove_game(game_id)

game_manager = GameManager()

# Менеджер пользователей
class UserManager:
    def __init__(self):
        self.conn = sqlite3.connect('games.db', check_same_thread=False)
    
    def get_or_create_user(self, user_id, chat_id, username):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        )
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                'INSERT INTO users (user_id, chat_id, username) VALUES (?, ?, ?)',
                (user_id, chat_id, username)
            )
            self.conn.commit()
        
        return user
    
    def update_stats(self, user_id, chat_id, game_type, won=True):
        cursor = self.conn.cursor()
        
        # Общая статистика
        if won:
            cursor.execute(
                'UPDATE users SET wins = wins + 1, points = points + 1 WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
        else:
            cursor.execute(
                'UPDATE users SET losses = losses + 1, points = points - 1 WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
        
        # Статистика по играм
        if won:
            cursor.execute(
                '''INSERT OR REPLACE INTO game_stats 
                (user_id, chat_id, game_type, wins, losses) 
                VALUES (?, ?, ?, COALESCE((SELECT wins FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), 0) + 1,
                COALESCE((SELECT losses FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), 0))''',
                (user_id, chat_id, game_type, user_id, chat_id, game_type, user_id, chat_id, game_type)
            )
        else:
            cursor.execute(
                '''INSERT OR REPLACE INTO game_stats 
                (user_id, chat_id, game_type, wins, losses) 
                VALUES (?, ?, ?, COALESCE((SELECT wins FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), 0),
                COALESCE((SELECT losses FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?), 0) + 1)''',
                (user_id, chat_id, game_type, user_id, chat_id, game_type, user_id, chat_id, game_type)
            )
        
        self.conn.commit()
    
    def get_user_stats(self, user_id, chat_id):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT username, wins, losses, points FROM users WHERE user_id = ? AND chat_id = ?',
            (user_id, chat_id)
        )
        return cursor.fetchone()
    
    def get_game_stats(self, user_id, chat_id, game_type):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT wins, losses FROM game_stats WHERE user_id = ? AND chat_id = ? AND game_type = ?',
            (user_id, chat_id, game_type)
        )
        return cursor.fetchone()

user_manager = UserManager()

# Клавиатуры
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="🎮 Выбрать игру", callback_data="select_game")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats"),
         InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top_players")],
        [InlineKeyboardButton(text="📖 Правила игр", callback_data="game_rules")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_games_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="🔫 Русская рулетка", callback_data="game_russian_roulette"),
         InlineKeyboardButton(text="🎲 Битва кубиков", callback_data="game_dice_battle")],
        [InlineKeyboardButton(text="🔢 Угадай число", callback_data="game_number_guess"),
         InInlineKeyboardButton(text="⭕ Крестики-нолики", callback_data="game_tic_tac_toe")],
        [InlineKeyboardButton(text="🧮 Быстрая математика", callback_data="game_quick_math"),
         InlineKeyboardButton(text="🪙 Бросок монеты", callback_data="game_coin_flip")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_play_again_keyboard(game_type):
    keyboard = [
        [InlineKeyboardButton(text="🎮 Играть снова", callback_data=f"game_{game_type}"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="my_stats")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команды
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_manager.get_or_create_user(message.from_user.id, message.chat.id, 
                                  message.from_user.username or message.from_user.first_name)
    
    text = (
        "🎮 **GameBot - Мини-игры для двоих!**\n\n"
        "💫 *6 увлекательных игр:*\n"
        "• 🔫 Русская рулетка (рандом)\n"
        "• 🎲 Битва кубиков (рандом)\n" 
        "• 🔢 Угадай число (навык)\n"
        "• ⭕ Крестики-нолики (стратегия)\n"
        "• 🧮 Быстрая математика (реакция)\n"
        "• 🪙 Бросок монеты (рандом)\n\n"
        "🎯 **Как играть:**\n"
        "1. Выбери игру\n"
        "2. Ответь на сообщение соперника\n"
        "3. Или упомяни @username\n\n"
        "Начни игру кнопкой ниже! 👇"
    )
    
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode='Markdown')

@dp.message(Command("games"))
async def games_command(message: types.Message):
    await message.answer("🎮 **Выбери игру:**", reply_markup=get_games_keyboard())

@dp.message(Command("play"))
async def play_command(message: types.Message):
    parts = message.text.split()
    if len(parts) > 1:
        game_type = parts[1]
        if game_type in ["russian_roulette", "dice_battle", "number_guess", "tic_tac_toe", "quick_math", "coin_flip"]:
            if message.reply_to_message:
                target_user = message.reply_to_message.from_user
                await start_specific_game(message, message.from_user, target_user, game_type)
                return
    
    await message.answer("❌ Использование: Ответь на сообщение командой `/play тип_игры`", parse_mode='Markdown')

# Обработчики callback
@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🎮 **GameBot - Главное меню**", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "select_game")
async def select_game(callback: types.CallbackQuery):
    await callback.message.edit_text("🎮 **Выбери игру:**", reply_markup=get_games_keyboard())

@dp.callback_query(F.data.startswith("game_"))
async def game_selected(callback: types.CallbackQuery):
    game_type = callback.data.replace("game_", "")
    
    if game_type in ["russian_roulette", "dice_battle", "number_guess", "tic_tac_toe", "quick_math", "coin_flip"]:
        await callback.message.edit_text(
            f"🎮 **{get_game_name(game_type)}**\n\n"
            f"💡 {get_game_description(game_type)}\n\n"
            f"**Чтобы начать:**\n"
            f"Ответь на сообщение соперника или упомяни @username",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.answer("❌ Игра не найдена!")

@dp.message(F.text.contains("@"))
async def handle_mention(message: types.Message):
    # Обработка упоминаний для вызова на игру
    if "игра" in message.text.lower() or "play" in message.text.lower():
        mentioned_users = [entity for entity in message.entities if entity.type == "mention"]
        if mentioned_users:
            await message.answer("🎮 Выбери игру для вызова:", reply_markup=get_games_keyboard())

# Запуск конкретной игры
async def start_specific_game(message: types.Message, initiator: types.User, target: types.User, game_type: str):
    if initiator.id == target.id:
        await message.reply("❌ Нельзя играть с самим собой!")
        return
    
    if target.is_bot:
        await message.reply("❌ Нельзя играть с ботом!")
        return
    
    initiator_name = initiator.username or initiator.first_name
    target_name = target.username or target.first_name
    
    game_id = game_manager.create_game(game_type, message.chat.id, initiator.id, target.id, initiator_name, target_name)
    user_manager.get_or_create_user(initiator.id, message.chat.id, initiator_name)
    user_manager.get_or_create_user(target.id, message.chat.id, target_name)
    
    # Запускаем соответствующую игру
    if game_type == "russian_roulette":
        await start_russian_roulette(message, game_id)
    elif game_type == "dice_battle":
        await start_dice_battle(message, game_id)
    elif game_type == "number_guess":
        await start_number_guess(message, game_id)
    elif game_type == "tic_tac_toe":
        await start_tic_tac_toe(message, game_id)
    elif game_type == "quick_math":
        await start_quick_math(message, game_id)
    elif game_type == "coin_flip":
        await start_coin_flip(message, game_id)

# Русская рулетка
async def start_russian_roulette(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"🔫 **Русская рулетка**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name}\n"
        f"• {player2_name}\n\n"
        f"💀 В револьвере 1 патрон из 6 камор\n"
        f"🎲 Ход: {player1_name}\n\n"
        f"Нажми кнопку чтобы выстрелить..."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💥 ВЫСТРЕЛИТЬ!", callback_data=f"rr_shoot_{game_id}")]
    ])
    
    await message.reply(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("rr_shoot_"))
async def rr_shoot(callback: types.CallbackQuery):
    game_id = callback.data.replace("rr_shoot_", "")
    game = game_manager.get_game(game_id)
    
    if not game:
        await callback.answer("❌ Игра завершена!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    if user_id not in game['players']:
        await callback.answer("❌ Вы не участник игры!", show_alert=True)
        return
    
    if not game['players'][user_id]['turn']:
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    # Определяем результат выстрела
    current_chamber = game['current_chamber']
    is_bullet = game['revolver'][current_chamber]
    
    player_name = game['players'][user_id]['name']
    game['current_chamber'] = (current_chamber + 1) % 6
    
    if is_bullet:
        # Игрок проиграл
        game['players'][user_id]['alive'] = False
        winner_id = [pid for pid in game['players'] if pid != user_id][0]
        winner_name = game['players'][winner_id]['name']
        
        # Обновляем статистику
        user_manager.update_stats(winner_id, game['chat_id'], "russian_roulette", won=True)
        user_manager.update_stats(user_id, game['chat_id'], "russian_roulette", won=False)
        
        text = (
            f"💥 **БАБАХ!**\n\n"
            f"💀 {player_name} был убит!\n"
            f"🏆 Победитель: {winner_name}\n\n"
            f"Патрон был в каморе {current_chamber + 1}"
        )
        
        await callback.message.edit_text(text, reply_markup=get_play_again_keyboard("russian_roulette"))
        game_manager.remove_game(game_id)
        
    else:
        # Игрок выжил, передаем ход
        game['players'][user_id]['turn'] = False
        next_player_id = [pid for pid in game['players'] if pid != user_id][0]
        game['players'][next_player_id]['turn'] = True
        next_player_name = game['players'][next_player_id]['name']
        
        text = (
            f"🔫 **Русская рулетка**\n\n"
            f"✅ {player_name} выжил!\n"
            f"🎲 Следующий ход: {next_player_name}\n"
            f"📍 Пройдено камор: {game['current_chamber']}\n\n"
            f"Следующий игрок, нажми кнопку..."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💥 ВЫСТРЕЛИТЬ!", callback_data=f"rr_shoot_{game_id}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

# Битва кубиков
async def start_dice_battle(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"🎲 **Битва кубиков**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name} (3 броска)\n"
        f"• {player2_name} (3 броска)\n\n"
        f"🎲 Ход: {player1_name}\n\n"
        f"Бросай кубик и набирай очки!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 БРОСИТЬ КУБИК", callback_data=f"db_roll_{game_id}")]
    ])
    
    await message.reply(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("db_roll_"))
async def db_roll(callback: types.CallbackQuery):
    game_id = callback.data.replace("db_roll_", "")
    game = game_manager.get_game(game_id)
    
    if not game:
        await callback.answer("❌ Игра завершена!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    if user_id not in game['players']:
        await callback.answer("❌ Вы не участник игры!", show_alert=True)
        return
    
    if user_id != game['current_player']:
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    # Бросаем кубик
    dice_roll = random.randint(1, 6)
    player = game['players'][user_id]
    player['score'] += dice_roll
    player['rolls_left'] -= 1
    
    player_name = player['name']
    
    if player['rolls_left'] > 0:
        # Еще есть броски
        text = (
            f"🎲 **Битва кубиков**\n\n"
            f"🎯 {player_name} выбросил: {dice_roll}
@dp.callback_query(F.data.startswith("db_roll_"))
async def db_roll(callback: types.CallbackQuery):
    game_id = callback.data.replace("db_roll_", "")
    game = game_manager.get_game(game_id)
    
    if not game:
        await callback.answer("❌ Игра завершена!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    if user_id not in game['players']:
        await callback.answer("❌ Вы не участник игры!", show_alert=True)
        return
    
    if user_id != game['current_player']:
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    # Бросаем кубик
    dice_roll = random.randint(1, 6)
    player = game['players'][user_id]
    player['score'] += dice_roll
    player['rolls_left'] -= 1
    
    player_name = player['name']
    player1_id, player2_id = list(game['players'].keys())
    player1 = game['players'][player1_id]
    player2 = game['players'][player2_id]
    
    if player['rolls_left'] > 0:
        # Еще есть броски
        text = (
            f"🎲 **Битва кубиков**\n\n"
            f"🎯 {player_name} выбросил: {dice_roll}\n"
            f"📊 Текущий счет: {player['score']}\n"
            f"🎲 Осталось бросков: {player['rolls_left']}\n\n"
            f"Бросай снова!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎲 БРОСИТЬ КУБИК", callback_data=f"db_roll_{game_id}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    else:
        # Броски закончились, передаем ход
        if game['current_player'] == player1_id:
            game['current_player'] = player2_id
            next_player_name = player2['name']
            
            text = (
                f"🎲 **Битва кубиков**\n\n"
                f"🎯 {player_name} выбросил: {dice_roll}\n"
                f"📊 Итоговый счет {player_name}: {player['score']}\n\n"
                f"🎲 Ход переходит к: {next_player_name}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎲 БРОСИТЬ КУБИК", callback_data=f"db_roll_{game_id}")]
            ])
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            
        else:
            # Оба игрока бросили, определяем победителя
            if player1['score'] > player2['score']:
                winner_id, loser_id = player1_id, player2_id
            elif player2['score'] > player1['score']:
                winner_id, loser_id = player2_id, player1_id
            else:
                # Ничья
                text = (
                    f"🎲 **Битва кубиков - НИЧЬЯ!**\n\n"
                    f"📊 Счет:\n"
                    f"• {player1['name']}: {player1['score']}\n"
                    f"• {player2['name']}: {player2['score']}\n\n"
                    f"🤝 Оба игрока получают по 1 очку!"
                )
                
                user_manager.update_stats(player1_id, game['chat_id'], "dice_battle", won=True)
                user_manager.update_stats(player2_id, game['chat_id'], "dice_battle", won=True)
                
                await callback.message.edit_text(text, reply_markup=get_play_again_keyboard("dice_battle"))
                game_manager.remove_game(game_id)
                return
            
            winner_name = game['players'][winner_id]['name']
            loser_name = game['players'][loser_id]['name']
            
            text = (
                f"🎲 **Битва кубиков - ПОБЕДА!**\n\n"
                f"🏆 Победитель: {winner_name}\n"
                f"📊 Счет:\n"
                f"• {player1['name']}: {player1['score']}\n"
                f"• {player2['name']}: {player2['score']}\n\n"
                f"🎯 {winner_name} получает 1 очко!"
            )
            
            user_manager.update_stats(winner_id, game['chat_id'], "dice_battle", won=True)
            user_manager.update_stats(loser_id, game['chat_id'], "dice_battle", won=False)
            
            await callback.message.edit_text(text, reply_markup=get_play_again_keyboard("dice_battle"))
            game_manager.remove_game(game_id)
    
    await callback.answer()

# Угадай число
async def start_number_guess(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"🔢 **Угадай число**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name}\n"
        f"• {player2_name}\n\n"
        f"🎲 Загадано число от 1 до 100\n"
        f"👤 Ход: {player1_name}\n\n"
        f"Отправь число от 1 до 100:"
    )
    
    await message.reply(text)

@dp.message(F.text & F.text.regexp(r'^\d+$'))
async def handle_number_guess(message: types.Message):
    # Ищем активную игру для этого пользователя в этом чате
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Ищем игру "Угадай число" где текущий ход этого пользователя
    for game_id, game in game_manager.active_games.items():
        if (game['type'] == "number_guess" and 
            game['chat_id'] == chat_id and 
            game['current_player'] == user_id):
            
            try:
                guess = int(message.text)
                if guess < 1 or guess > 100:
                    await message.reply("❌ Число должно быть от 1 до 100!")
                    return
                
                target_number = game['target_number']
                player_name = game['players'][user_id]['name']
                game['players'][user_id]['attempts'] += 1
                
                if guess == target_number:
                    # Игрок угадал!
                    winner_id = user_id
                    loser_id = [pid for pid in game['players'] if pid != user_id][0]
                    winner_name = game['players'][winner_id]['name']
                    loser_name = game['players'][loser_id]['name']
                    attempts = game['players'][user_id]['attempts']
                    
                    text = (
                        f"🔢 **Угадай число - ПОБЕДА!**\n\n"
                        f"🎯 Загаданное число: {target_number}\n"
                        f"🏆 Победитель: {winner_name}\n"
                        f"📊 Попыток: {attempts}\n\n"
                        f"🎯 {winner_name} угадал число!"
                    )
                    
                    user_manager.update_stats(winner_id, game['chat_id'], "number_guess", won=True)
                    user_manager.update_stats(loser_id, game['chat_id'], "number_guess", won=False)
                    
                    await message.reply(text, reply_markup=get_play_again_keyboard("number_guess"))
                    game_manager.remove_game(game_id)
                    
                else:
                    # Не угадал, передаем ход
                    hint = "🔻 Меньше" if guess > target_number else "🔺 Больше"
                    next_player_id = [pid for pid in game['players'] if pid != user_id][0]
                    game['current_player'] = next_player_id
                    next_player_name = game['players'][next_player_id]['name']
                    
                    text = (
                        f"🔢 **Угадай число**\n\n"
                        f"🎯 {player_name}: {guess} {hint}\n"
                        f"📊 Попыток: {game['players'][user_id]['attempts']}\n\n"
                        f"👤 Следующий ход: {next_player_name}\n\n"
                        f"Отправь число от 1 до 100:"
                    )
                    
                    await message.reply(text)
                
                break
                
            except ValueError:
                await message.reply("❌ Введи корректное число!")
            break

# Крестики-нолики
async def start_tic_tac_toe(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"⭕ **Крестики-нолики**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name} (❌)\n"
        f"• {player2_name} (⭕)\n\n"
        f"🎲 Ход: {player1_name}\n\n"
        f"Выбери клетку:"
    )
    
    keyboard = get_tic_tac_toe_keyboard(game_id, game['board'])
    await message.reply(text, reply_markup=keyboard)

def get_tic_tac_toe_keyboard(game_id: str, board: list):
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            cell_index = i + j
            row.append(InlineKeyboardButton(
                text=board[cell_index],
                callback_data=f"ttt_{game_id}_{cell_index}"
            ))
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(F.data.startswith("ttt_"))
async def ttt_move(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    game_id = parts[1]
    cell_index = int(parts[2])
    
    game = game_manager.get_game(game_id)
    if not game:
        await callback.answer("❌ Игра завершена!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    if user_id not in game['players']:
        await callback.answer("❌ Вы не участник игры!", show_alert=True)
        return
    
    if user_id != game['current_player']:
        await callback.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    if game['board'][cell_index] != '⬜':
        await callback.answer("❌ Клетка уже занята!", show_alert=True)
        return
    
    # Делаем ход
    symbol = game['players'][user_id]['symbol']
    game['board'][cell_index] = symbol
    player_name = game['players'][user_id]['name']
    
    # Проверяем победу
    if check_tic_tac_toe_win(game['board'], symbol):
        # Игрок победил
        winner_id = user_id
        loser_id = [pid for pid in game['players'] if pid != user_id][0]
        winner_name = game['players'][winner_id]['name']
        loser_name = game['players'][loser_id]['name']
        
        text = (
            f"⭕ **Крестики-нолики - ПОБЕДА!**\n\n"
            f"🏆 Победитель: {winner_name} ({symbol})\n"
            f"💀 Проигравший: {loser_name}\n\n"
            f"🎯 {winner_name} выиграл партию!"
        )
        
        user_manager.update_stats(winner_id, game['chat_id'], "tic_tac_toe", won=True)
        user_manager.update_stats(loser_id, game['chat_id'], "tic_tac_toe", won=False)
        
        keyboard = get_tic_tac_toe_keyboard(game_id, game['board'])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.message.reply("🎮 Игра завершена!", reply_markup=get_play_again_keyboard("tic_tac_toe"))
        game_manager.remove_game(game_id)
        
    elif '⬜' not in game['board']:
        # Ничья
        player1_id, player2_id = list(game['players'].keys())
        
        text = f"⭕ **Крестики-нолики - НИЧЬЯ!**\n\n🤝 Партия завершилась вничью!"
        
        user_manager.update_stats(player1_id, game['chat_id'], "tic_tac_toe", won=True)
        user_manager.update_stats(player2_id, game['chat_id'], "tic_tac_toe", won=True)
        
        keyboard = get_tic_tac_toe_keyboard(game_id, game['board'])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.message.reply("🎮 Игра завершена!", reply_markup=get_play_again_keyboard("tic_tac_toe"))
        game_manager.remove_game(game_id)
        
    else:
        # Продолжаем игру
        next_player_id = [pid for pid in game['players'] if pid != user_id][0]
        game['current_player'] = next_player_id
        next_player_name = game['players'][next_player_id]['name']
        next_symbol = game['players'][next_player_id]['symbol']
        
        text = (
            f"⭕ **Крестики-нолики**\n\n"
            f"🎯 Ход сделал: {player_name} ({symbol})\n"
            f"🎲 Следующий ход: {next_player_name} ({next_symbol})"
        )
        
        keyboard = get_tic_tac_toe_keyboard(game_id, game['board'])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

def check_tic_tac_toe_win(board, symbol):
    # Проверяем все выигрышные комбинации
    win_combinations = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Горизонтальные
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Вертикальные
        [0, 4, 8], [2, 4, 6]              # Диагональные
    ]
    
    for combo in win_combinations:
        if board[combo[0]] == symbol and board[combo[1]] == symbol and board[combo[2]] == symbol:
            return True
    return False

# Быстрая математика
async def start_quick_math(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"🧮 **Быстрая математика**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name}\n"
        f"• {player2_name}\n\n"
        f"🎲 Ход: {player1_name}\n\n"
        f"Реши пример:\n"
        f"**{game['problem']} = ?**\n\n"
        f"Отправь ответ числом:"
    )
    
    await message.reply(text, parse_mode='Markdown')

@dp.message(F.text & F.text.regexp(r'^-?\d+$'))
async def handle_math_answer(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Ищем активную игру "Быстрая математика"
    for game_id, game in game_manager.active_games.items():
        if (game['type'] == "quick_math" and 
            game['chat_id'] == chat_id and 
            game['current_player'] == user_id):
            
            try:
                answer = int(message.text)
                correct_answer = game['answer']
                player_name = game['players'][user_id]['name']
                
                if answer == correct_answer:
                    # Правильный ответ
                    game['players'][user_id]['score'] += 1
                    player1_id, player2_id = list(game['players'].keys())
                    player1 = game['players'][player1_id]
                    player2 = game['players'][player2_id]
                    
                    if player1['score'] >= 3 or player2['score'] >= 3:
                        # Кто-то достиг 3 очков
                        if player1['score'] >= 3:
                            winner_id, loser_id = player1_id, player2_id
                        else:
                            winner_id, loser_id = player2_id, player1_id
                        
                        winner_name = game['players'][winner_id]['name']
                        loser_name = game['players'][loser_id]['name']
                        
                        text = (
                            f"🧮 **Быстрая математика - ПОБЕДА!**\n\n"
                            f"🏆 Победитель: {winner_name}\n"
                            f"📊 Счет:\n"
                            f"• {player1['name']}: {player1['score']}\n"
                            f"• {player2['name']}: {player2['score']}\n\n"
                            f"🎯 {winner_name} быстрее решает примеры!"
                        )
                        
                        user_manager.update_stats(winner_id, game['chat_id'], "quick_math", won=True)
                        user_manager.update_stats(loser_id, game['chat_id'], "quick_math", won=False)
                        
                        await message.reply(text, reply_markup=get_play_again_keyboard("quick_math"))
                        game_manager.remove_game(game_id)
                        
                    else:
                        # Генерируем новый пример
                        num1, num2 = random.randint(1, 20), random.randint(1, 20)
                        operations = ['+', '-', '*']
                        operation = random.choice(operations)
                        
                        if operation == '+':
                            new_answer = num1 + num2
                        elif operation == '-':
                            new_answer = num1 - num2
                        else:
                            new_answer = num1 * num2
                        
                        game['problem'] = f"{num1} {operation} {num2}"
                        game['answer'] = new_answer
                        
                        # Передаем ход
                        next_player_id = [pid for pid in game['players'] if pid != user_id][0]
                        game['current_player'] = next_player_id
                        next_player_name = game['players'][next_player_id]['name']
                        
                        text = (
                            f"🧮 **Быстрая математика**\n\n"
                            f"✅ {player_name} ответил правильно!\n"
                            f"📊 Счет:\n"
                            f"• {player1['name']}: {player1['score']}\n"
                            f"• {player2['name']}: {player2['score']}\n\n"
                            f"🎲 Следующий ход: {next_player_name}\n\n"
                            f"Реши пример:\n"
                            f"**{game['problem']} = ?**"
                        )
                        
                        await message.reply(text, parse_mode='Markdown')
                        
                else:
                    # Неправильный ответ
                    next_player_id = [pid for pid in game['players'] if pid != user_id][0]
                    game['current_player'] = next_player_id
                    next_player_name = game['players'][next_player_id]['name']
                    
                    text = (
                        f"🧮 **Быстрая математика**\n\n"
                        f"❌ {player_name} ответил неправильно!\n"
                        f"✅ Правильный ответ: {correct_answer}\n\n"
                        f"🎲 Следующий ход: {next_player_name}\n\n"
                        f"Реши пример:\n"
                        f"**{game['problem']} = ?**"
                    )
                    
                    await message.reply(text, parse_mode='Markdown')
                
                break
                
            except ValueError:
                await message.reply("❌ Введи корректное число!")
            break

# Бросок монеты
async def start_coin_flip(message: types.Message, game_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        return
    
    player1_id, player2_id = list(game['players'].keys())
    player1_name = game['players'][player1_id]['name']
    player2_name = game['players'][player2_id]['name']
    
    text = (
        f"🪙 **Бросок монеты**\n\n"
        f"🎯 Игроки:\n"
        f"• {player1_name}\n"
        f"• {player2_name}\n\n"
        f"Выбери сторону монеты:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🦅 Орел", callback_data=f"cf_choice_{game_id}_heads"),
            InlineKeyboardButton(text="📀 Решка", callback_data=f"cf_choice_{game_id}_tails")
        ]
    ])
    
    await message.reply(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("cf_choice_"))
async def cf_choice(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    game_id = parts[2]
    choice = parts[3]  # heads или tails
    
    game = game_manager.get_game(game_id)
    if not game:
        await callback.answer("❌ Игра завершена!", show_alert=True)
        return
    
    user_id = callback.from_user.id
    if user_id not in game['players']:
        await callback.answer("❌ Вы не участник игры!", show_alert=True)
        return
    
    # Записываем выбор игрока
    game['players'][user_id]['choice'] = choice
    player_name = game['players'][user_id]['name']
    
    # Проверяем, сделали ли оба игрока выбор
    player1_id, player2_id = list(game['players'].keys())
    player1_choice = game['players'][player1_id]['choice']
    player2_choice = game['players'][player2_id]['choice']
    
    if player1_choice and player2_choice:
        # Оба сделали выбор, подбрасываем монету
        result = random.choice(['heads', 'tails'])
        result_emoji = '🦅' if result == 'heads' else '📀'
        
        # Определяем победителя
        if player1_choice == result:
            winner_id, loser_id = player1_id, player2_id
        else:
            winner_id, loser_id = player2_id, player1_id
        
        winner_name = game['players'][winner_id]['name']
        loser_name = game['players'][loser_id]['name']
        
        text = (
            f"🪙 **Бросок монеты**\n\n"
            f"🎯 Результат: {result_emoji} {'Орел' if result == 'heads' else 'Решка'}\n\n"
            f"🏆 Победитель: {winner_name}\n"
            f"💀 Проигравший: {loser_name}\n\n"
            f"Выборы:\n"
            f"• {game['players'][player1_id]['name']}: {'Орел' if player1_choice == 'heads' else 'Решка'}\n"
            f"• {game['players'][player2_id]['name']}: {'Орел' if player2_choice == 'heads' else 'Решка'}"
        )
        
        user_manager.update_stats(winner_id, game['chat_id'], "coin_flip", won=True)
        user_manager.update_stats(loser_id, game['chat_id'], "coin_flip", won=False)
        
        await callback.message.edit_text(text, reply_markup=get_play_again_keyboard("coin_flip"))
        game_manager.remove_game(game_id)
        
    else:
        # Ждем второго игрока
        text = (
            f"🪙 **Бросок монеты**\n\n"
            f"✅ {player_name} выбрал: {'Орел' if choice == 'heads' else 'Решка'}\n"
            f"⏳ Ожидаем выбор второго игрока..."
        )
        
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup)
        await callback.answer(f"✅ Ты выбрал {'Орел' if choice == 'heads' else 'Решка'}!")

# Вспомогательные функции
def get_game_name(game_type: str) -> str:
    names = {
        "russian_roulette": "🔫 Русская рулетка",
        "dice_battle": "🎲 Битва кубиков", 
        "number_guess": "🔢 Угадай число",
        "tic_tac_toe": "⭕ Крестики-нолики",
        "quick_math": "🧮 Быстрая математика",
        "coin_flip": "🪙 Бросок монеты"
    }
    return names.get(game_type, "Неизвестная игра")

def get_game_description(game_type: str) -> str:
    descriptions = {
        "russian_roulette": "Смертельная игра на удачу. 1 патрон, 6 камор. Кто выживет?",
        "dice_battle": "Бросай кубики и набирай очки. У кого будет больше?",
        "number_guess": "Угадай загаданное число. Меньше попыток - больше шансов!",
        "tic_tac_toe": "Классическая игра в крестики-нолики. Прояви стратегию!",
        "quick_math": "Решай примеры на скорость. Первый до 3 очков побеждает!",
        "coin_flip": "Простая игра на удачу. Выбери сторону монеты!"
    }
    return descriptions.get(game_type, "Описание недоступно")

# Статистика
@dp.callback_query(F.data == "my_stats")
async def my_stats(callback: types.CallbackQuery):
    user_stats = user_manager.get_user_stats(callback.from_user.id, callback.message.chat.id)
    
    if user_stats:
        username, wins, losses, points = user_stats
        
        # Получаем статистику по играм
        cursor = user_manager.conn.cursor()
        cursor.execute(
            'SELECT game_type, wins, losses FROM game_stats WHERE user_id = ? AND chat_id = ?',
            (callback.from_user.id, callback.message.chat.id)
        )
        game_stats = cursor.fetchall()
        
        text = f"📊 **Статистика {username}**\n\n"
        text += f"🏆 Побед: {wins}\n"
        text += f"💀 Поражений: {losses}\n" 
        text += f"🎯 Очков: {points}\n\n"
        
        if game_stats:
            text += "**Статистика по играм:**\n"
            for game_type, game_wins, game_losses in game_stats:
                game_name = get_game_name(game_type)
                total = game_wins + game_losses
                win_rate = (game_wins / total * 100) if total > 0 else 0
                text += f"• {game_name}: {game_wins}/{total} ({win_rate:.1f}%)\n"
        
        await callback.message.edit_text(text, reply_markup=get_main_keyboard())
    else:
        await callback.message.edit_text("📊 Статистика не найдена. Сыграй в свою первую игру!", 
                                       reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "top_players")
async def top_players(callback: types.CallbackQuery):
    cursor = user_manager.conn.cursor()
    cursor.execute(
        'SELECT username, wins, losses, points FROM users WHERE chat_id = ? ORDER BY points DESC LIMIT 10',
        (callback.message.chat.id,)
    )
    top_users = cursor.fetchall()
    
    if top_users:
        text = "🏆 **Топ игроков чата:**\n\n"
        for i, (username, wins, losses, points) in enumerate(top_users, 1):
            text += f"{i}. {username} - {points} очков ({wins}🏆/{losses}💀)\n"
    else:
        text = "🏆 В этом чате еще нет игроков!\nСыграй в первую игру!"
    
    await callback.message.edit_text(text, reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "game_rules")
async def game_rules(callback: types.CallbackQuery):
    text = (
        "📖 **Правила игр:**\n\n"
        "🔫 **Русская рулетка:**\n"
        "• 1 патрон в 6-зарядном револьвере\n"
        "• Игроки по очереди стреляют в себя\n"
        "• Проигрывает тот, в кого попадет патрон\n\n"
        
        "🎲 **Битва кубиков:**\n"
        "• Каждый игрок бросает кубик 3 раза\n"
        "• Суммируются результаты бросков\n"
        "• Побеждает игрок с большей суммой\n\n"
        
        "🔢 **Угадай число:**\n"
        "• Загадано число от 1 до 100\n"
        "• Игроки по очереди называют числа\n"
        "• Получают подсказки 'больше/меньше'\n"
        "• Побеждает угадавший число\n\n"
        
        "⭕ **Крестики-нолики:**\n"
        "• Классическая игра 3x3\n"
        "• Собирай 3 в ряд по горизонтали, вертикали или диагонали\n\n"
        
        "🧮 **Быстрая математика:**\n"
        "• Решай простые математические примеры\n"
        "• Первый до 3 правильных ответов побеждает\n\n"
        
        "🪙 **Бросок монеты:**\n"
        "• Игроки выбирают сторону монеты\n"
        "• Подбрасывается виртуальная монета\n"
        "• Побеждает угадавший сторону"
    )
    
    await callback.message.edit_text(text, reply_markup=get_main_keyboard())

# Запуск бота
async def main():
    logger.info("🚀 GameBot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())