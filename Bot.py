import logging
import sqlite3
import threading
from datetime import datetime
from telebot import TeleBot, types
import time
import os
import sys
import requests
from requests.exceptions import RequestException

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация бота
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789  # Замените на ваш ID администратора
CHANNEL_URL = "https://t.me/your_channel"

# Полный список из 89 серверов Black Russia
SERVERS = [
    "RED", "GREEN", "BLUE", "YELLOW", "ORANGE", "PURPLE", "LIME", "PINK",
    "CHERRY", "BLACK", "INDIGO", "WHITE", "MAGENTA", "CRIMSON", "GOLD", "AZURE",
    "PLATINUM", "AQUA", "GRAY", "ICE", "CHILLI", "CHOCO", "MOSCOW", "SPB",
    "UFA", "SOCHI", "KAZAN", "SAMARA", "ROSTOV", "ANAPA", "EKB", "KRASNODAR",
    "ARZAMAS", "NOVOSIB", "GROZNY", "SARATOV", "OMSK", "IRKUTSK", "VOLGOGRAD", "VORONEZH",
    "BELGOROD", "MAKHACHKALA", "VLADIKAVKAZ", "VLADIVOSTOK", "KALININGRAD", "CHELYABINSK", "KRASNOYARSK", "CHEBOKSARY",
    "KHABAROVSK", "PERM", "TULA", "RYAZAN", "MURMANSK", "PENZA", "KURSK", "ARKHANGELSK",
    "ORENBURG", "KIROV", "KEMEROVO", "TYUMEN", "TOLYATTI", "IVANOVO", "STAVROPOL", "SMOLENSK",
    "PSKOV", "BRYANSK", "OREL", "YAROSLAVL", "BARNAUL", "LIPETSK", "ULYANOVSK", "YAKUTSK",
    "TAMBOV", "BRATSK", "ASTRAKHAN", "CHITA", "KOSTROMA", "VLADIMIR", "KALUGA", "NOVGOROD",
    "TAGANROG", "VOLOGDA", "TVER", "TOMSK", "IZHEVSK", "SURGUT", "PODOLSK", "MAGADAN",
    "CHEREPOVETS"
]

class BotManager:
    def __init__(self, token):
        self.token = token
        self.bot = None
        self.restart_count = 0
        self.max_restarts = 10
        self.init_bot()
    
    def init_bot(self):
        """Инициализация бота с обработчиками"""
        try:
            self.bot = TeleBot(self.token)
            self.setup_handlers()
            logger.info("Бот инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации бота: {e}")
            raise
    
    def setup_handlers(self):
        """Настройка всех обработчиков"""
        
        @self.bot.message_handler(commands=['start', 'restart'])
        def start_command(message):
            try:
                user = message.from_user
                self.add_user(user.id, user.username, user.first_name, user.last_name)
                self.log_action(user.id, 'start_command')
                
                if user.id == ADMIN_ID:
                    self.bot.send_message(message.chat.id, "👑 Добро пожаловать в админ-панель!", 
                                        reply_markup=self.admin_menu())
                else:
                    self.bot.send_message(
                        message.chat.id,
                        "🤖 Добро пожаловать в бот для привязки аккаунтов Black Russia!\n\n"
                        "Выберите действие:",
                        reply_markup=self.main_menu()
                    )
            except Exception as e:
                logger.error(f"Ошибка в start_command: {e}")
                self.send_error_message(message.chat.id)
        
        @self.bot.message_handler(func=lambda message: message.text == '📢 Наш канал')
        def channel_command(message):
            try:
                self.log_action(message.from_user.id, 'channel_click')
                self.bot.send_message(
                    message.chat.id,
                    f"📢 Перейдите в наш канал: {CHANNEL_URL}",
                    reply_markup=self.main_menu()
                )
            except Exception as e:
                logger.error(f"Ошибка в channel_command: {e}")
                self.send_error_message(message.chat.id)
        
        # Добавьте остальные обработчики аналогично...
        
        @self.bot.message_handler(func=lambda message: message.text in SERVERS)
        def server_selected(message):
            try:
                user = message.from_user
                server = message.text
                self.log_action(user.id, f'server_selected: {server}')
                
                binding_id = self.create_binding(user.id, server)
                
                user_msg = self.bot.send_message(
                    message.chat.id,
                    f"✅ Сервер **{server}** найден!\n🔄 Генерируется процесс привязки, ожидайте...",
                    parse_mode='Markdown',
                    reply_markup=self.main_menu()
                )
                
                admin_msg = self.bot.send_message(
                    ADMIN_ID,
                    f"🔔 Новая заявка на привязку!\n\n"
                    f"👤 Пользователь: @{user.username if user.username else 'нет'}\n"
                    f"🆔 ID: {user.id}\n"
                    f"🎮 Сервер: {server}\n"
                    f"🕒 Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}\n\n"
                    f"💬 Ответьте на это сообщение чтобы отправить ответ пользователю."
                )
                
                self.update_binding_messages(binding_id, user_msg.message_id, admin_msg.message_id)
                
            except Exception as e:
                logger.error(f"Ошибка в server_selected: {e}")
                self.send_error_message(message.chat.id)
        
        @self.bot.message_handler(func=lambda message: message.reply_to_message and message.from_user.id == ADMIN_ID)
        def admin_reply(message):
            try:
                original_message = message.reply_to_message
                result = self.get_binding_by_admin_message(original_message.message_id)
                
                if result:
                    user_id, user_message_id = result
                    self.bot.send_message(user_id, message.text)
                    self.bot.send_message(ADMIN_ID, "✅ Сообщение доставлено пользователю")
                    self.log_action(ADMIN_ID, f'admin_reply_sent: {user_id}')
                else:
                    self.bot.send_message(ADMIN_ID, "❌ Не удалось найти заявку")
                    
            except Exception as e:
                logger.error(f"Ошибка в admin_reply: {e}")
                self.bot.send_message(ADMIN_ID, f"❌ Ошибка при отправке: {str(e)}")
    
    def send_error_message(self, chat_id):
        """Отправка сообщения об ошибке пользователю"""
        try:
            self.bot.send_message(
                chat_id,
                "⚠️ Произошла временная ошибка. Пожалуйста, попробуйте позже.",
                reply_markup=self.main_menu()
            )
        except:
            pass
    
    def safe_polling(self):
        """Безопасный запуск polling с перезапуском при ошибках"""
        while self.restart_count < self.max_restarts:
            try:
                logger.info(f"Запуск бота (попытка {self.restart_count + 1})")
                self.bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
                
            except RequestException as e:
                logger.warning(f"Ошибка сети: {e}. Перезапуск через 10 секунд...")
                self.restart_count += 1
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Критическая ошибка: {e}. Перезапуск через 30 секунд...")
                self.restart_count += 1
                time.sleep(30)
        
        logger.error("Достигнуто максимальное количество перезапусков. Бот остановлен.")
    
    # Методы для работы с БД (аналогичные предыдущим)
    def init_db(self):
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                server TEXT,
                status TEXT,
                created_at TEXT,
                admin_message_id INTEGER,
                user_message_id INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_text TEXT,
                timestamp TEXT
            )
        ''')
        
        conn.commit()
        return conn
    
    def log_action(self, user_id, action):
        try:
            cursor = self.db_connection.cursor()
            cursor.execute(
                "INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)",
                (user_id, action, datetime.now().isoformat())
            )
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Ошибка записи лога: {e}")
    
    def add_user(self, user_id, username, first_name, last_name):
        try:
            cursor = self.db_connection.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, registered_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, first_name, last_name, datetime.now().isoformat())
            )
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
    
    # Добавьте остальные методы БД...
    
    def main_menu(self):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('🔗 Привязать аккаунт')
        btn2 = types.KeyboardButton('📢 Наш канал')
        markup.add(btn1, btn2)
        return markup
    
    def servers_menu(self):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
        
        buttons = []
        for server in SERVERS:
            buttons.append(types.KeyboardButton(server))
            if len(buttons) == 4:
                markup.add(*buttons)
                buttons = []
        
        if buttons:
            markup.add(*buttons)
        
        btn_back = types.KeyboardButton('⬅️ Назад')
        markup.add(btn_back)
        return markup
    
    def admin_menu(self):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn1 = types.KeyboardButton('📊 Статистика')
        btn2 = types.KeyboardButton('📢 Рассылка')
        btn3 = types.KeyboardButton('📋 Логи')
        btn4 = types.KeyboardButton('⬅️ Главное меню')
        markup.add(btn1, btn2, btn3, btn4)
        return markup

# Запуск бота
if __name__ == "__main__":
    logger.info("=== ЗАПУСК УЛУЧШЕННОГО БОТА ===")
    
    try:
        bot_manager = BotManager(BOT_TOKEN)
        bot_manager.db_connection = bot_manager.init_db()
        bot_manager.safe_polling()
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске: {e}")
        sys.exit(1)
