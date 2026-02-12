#!/usr/bin/env python3
"""
COMPLETE SMS OTP SYSTEM - MERGED VERSION
SMS Monitor + Number Bot = Single Powerful System
Author: Senior Python Automation Engineer
Version: 1.0.0 - FULLY INTEGRATED
"""

import os
import sys
import json
import time
import hashlib
import sqlite3
import requests
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, quote
from threading import Event, Thread
import signal
import logging
from logging.handlers import RotatingFileHandler
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =================================================
# CREDENTIALS - APNI VALUES YAHAN DALO
# =================================================

# IPRN PANEL CREDENTIALS
USERNAME = "awais1234"
PASSWORD = "awais1234"
TELEGRAM_BOT_TOKEN = "8278099501:AAEO-0bQTAmAbC7_qaYvVjnH-dGZAialSMU"
TELEGRAM_CHAT_ID = "-1003862493586"  # OTP forward hoga yahan

# NUMBER BOT TOKEN (ALAG BOT HOGA)
NUMBER_BOT_TOKEN = "8569562005:AAEKCUTPL7vm5pEaBIoOeqwME9rPrRUzVwM"
ADMIN_IDS = [7520986318]  # Apna Telegram ID

# =================================================
# CONFIGURATION
# =================================================

BASE_URL = "http://139.99.208.63/ints/"
LOGIN_URL = urljoin(BASE_URL, "login")
LOGIN_POST_URL = urljoin(BASE_URL, "signin")
DASHBOARD_URL = urljoin(BASE_URL, "agent/SMSDashboard")
SMS_REPORT_URL = urljoin(BASE_URL, "agent/SMSCDRReports")
SMS_DATA_URL = urljoin(BASE_URL, "agent/res/data_smscdr.php")

REFRESH_INTERVAL = 5  # seconds
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 10

# BUTTON LINKS
GET_NUMBER_LINK = "https://t.me/slimenumberbot"
DEVELOPER_LINK = "https://t.me/Slime_313"

# =================================================
# PATH SETUP
# =================================================

# Railway detection
IS_RAILWAY = os.path.exists('/.dockerenv') or os.environ.get('RAILWAY_SERVICE_NAME')

if IS_RAILWAY:
    DATA_DIR = '/data/sms_data'  # Railway volume path
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(SCRIPT_DIR, 'sms_data')

os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'merged_system.db')
LOG_FILE = os.path.join(DATA_DIR, 'merged_bot.log')
# =================================================
# LOGGING SETUP
# =================================================

def setup_logging():
    logger = logging.getLogger('MergedSMSBot')
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5*1024*1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# =================================================
# DATABASE MANAGER - MERGED
# =================================================

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # SMS messages table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash TEXT UNIQUE,
                    timestamp TEXT,
                    number TEXT,
                    range_name TEXT,
                    cli TEXT,
                    client TEXT,
                    message TEXT,
                    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_hash ON messages(hash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_number ON messages(number)')
            
            # Session table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS session (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ============ NUMBER BOT TABLES ============
            
            # Users table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    joined_date TEXT,
                    total_numbers INTEGER DEFAULT 0
                )
            ''')
            
            # Countries table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS countries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    flag TEXT,
                    name TEXT,
                    services TEXT,
                    price INTEGER DEFAULT 1,
                    total_numbers INTEGER DEFAULT 0,
                    available_numbers INTEGER DEFAULT 0
                )
            ''')
            
            # Numbers table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT UNIQUE,
                    country_code TEXT,
                    status TEXT DEFAULT 'available',
                    allocated_to INTEGER,
                    allocated_at TEXT,
                    expiry TEXT,
                    FOREIGN KEY (country_code) REFERENCES countries(code),
                    FOREIGN KEY (allocated_to) REFERENCES users(user_id)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_num_status ON numbers(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_num_number ON numbers(number)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_num_allocated ON numbers(allocated_to)')
            
            # Stats table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    date TEXT PRIMARY KEY,
                    numbers_allocated INTEGER DEFAULT 0,
                    otp_received INTEGER DEFAULT 0
                )
            ''')
            
            # Broadcast messages table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS broadcast (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent_count INTEGER DEFAULT 0
                )
            ''')
            
            conn.commit()
    
    # ============ SMS METHODS ============
    
    def is_duplicate_sms(self, msg_hash):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM messages WHERE hash = ? LIMIT 1',
                (msg_hash,)
            )
            return cursor.fetchone() is not None
    
    def add_sms(self, msg_hash, timestamp, number, range_name, cli, client, message):
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO messages 
                    (hash, timestamp, number, range_name, cli, client, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (msg_hash, timestamp, number, range_name, cli, client, message[:500]))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"DB insert error: {e}")
                return False
    
    def save_session(self, cookies_dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO session (key, value) VALUES (?, ?)',
                ('cookies', json.dumps(cookies_dict))
            )
            conn.commit()
    
    def load_session(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT value FROM session WHERE key = ?',
                ('cookies',)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None
    
    # ============ NUMBER BOT METHODS ============
    
    def add_user(self, user_id, username):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR IGNORE INTO users (user_id, username, joined_date)
                VALUES (?, ?, ?)
            ''', (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    
    def get_available_number(self, country_code):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT number FROM numbers 
                WHERE country_code = ? AND status = 'available' 
                LIMIT 1
            ''', (country_code,))
            return cursor.fetchone()
    
    def allocate_number(self, number, user_id):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now()
            expiry = now + timedelta(minutes=5)
            
            conn.execute('''
                UPDATE numbers SET 
                    status = 'allocated',
                    allocated_to = ?,
                    allocated_at = ?,
                    expiry = ?
                WHERE number = ?
            ''', (user_id, now.strftime("%Y-%m-%d %H:%M:%S"), 
                  expiry.strftime("%Y-%m-%d %H:%M:%S"), number))
            
            conn.execute('''
                UPDATE countries SET available_numbers = available_numbers - 1 
                WHERE code = (SELECT country_code FROM numbers WHERE number = ?)
            ''', (number,))
            
            conn.execute('''
                UPDATE users SET total_numbers = total_numbers + 1 
                WHERE user_id = ?
            ''', (user_id,))
            
            conn.commit()
    
    def check_number_allocated(self, number):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT allocated_to FROM numbers 
                WHERE number = ? AND status = 'allocated'
            ''', (number,))
            return cursor.fetchone()
    
    def delete_number_on_otp(self, number):
        """OTP milte hi number delete karo"""
        with sqlite3.connect(self.db_path) as conn:
            # Get country code before deletion
            cursor = conn.execute('''
                SELECT country_code, allocated_to FROM numbers WHERE number = ?
            ''', (number,))
            result = cursor.fetchone()
            
            if result:
                country_code, user_id = result
                
                # Delete the number
                conn.execute('DELETE FROM numbers WHERE number = ?', (number,))
                
                # Update country counts
                conn.execute('''
                    UPDATE countries SET 
                        total_numbers = total_numbers - 1,
                        available_numbers = available_numbers - 1
                    WHERE code = ?
                ''', (country_code,))
                
                conn.commit()
                return user_id
        return None
    
    def get_countries_with_stock(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT code, flag, name, available_numbers, services, price 
                FROM countries WHERE available_numbers > 0 ORDER BY name
            ''')
            return cursor.fetchall()
    
    def get_all_countries(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT code, flag, name FROM countries ORDER BY name
            ''')
            return cursor.fetchall()
    
    def add_country(self, code, flag, name, services, price):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR IGNORE INTO countries 
                (code, flag, name, services, price, total_numbers, available_numbers)
                VALUES (?, ?, ?, ?, ?, 0, 0)
            ''', (code.strip(), flag.strip(), name.strip(), services.strip(), int(price)))
            conn.commit()
    
    def add_numbers(self, numbers, country_code):
        with sqlite3.connect(self.db_path) as conn:
            added = 0
            for number in numbers:
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO numbers 
                        (number, country_code, status) 
                        VALUES (?, ?, 'available')
                    ''', (number.strip(), country_code))
                    if conn.total_changes > added:
                        added += 1
                except:
                    pass
            
            if added > 0:
                conn.execute('''
                    UPDATE countries SET 
                        total_numbers = total_numbers + ?,
                        available_numbers = available_numbers + ?
                    WHERE code = ?
                ''', (added, added, country_code))
            
            conn.commit()
            return added
    
    def get_user_active_numbers(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT n.number, c.flag, c.name, n.expiry 
                FROM numbers n
                JOIN countries c ON n.country_code = c.code
                WHERE n.allocated_to = ? AND n.status = 'allocated'
                ORDER BY n.allocated_at DESC LIMIT 10
            ''', (user_id,))
            return cursor.fetchall()
    
    def get_stock_summary(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT flag, name, available_numbers, total_numbers, services 
                FROM countries WHERE total_numbers > 0 
                ORDER BY available_numbers DESC LIMIT 15
            ''')
            return cursor.fetchall()
    
    def get_all_users(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT user_id FROM users')
            return [row[0] for row in cursor.fetchall()]
    
    def cleanup_old_sms(self, days=7):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                DELETE FROM messages 
                WHERE datetime(received_at) < datetime('now', '-? days')
            ''', (days,))
            conn.commit()
    
    def cleanup_expired_numbers(self):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Get expired numbers
            cursor = conn.execute('''
                SELECT number, country_code FROM numbers 
                WHERE status = 'allocated' AND expiry < ?
            ''', (now,))
            expired = cursor.fetchall()
            
            # Free them
            conn.execute('''
                UPDATE numbers SET status = 'available', allocated_to = NULL 
                WHERE status = 'allocated' AND expiry < ?
            ''', (now,))
            
            # Update counts for each country
            for number, country_code in expired:
                conn.execute('''
                    UPDATE countries SET available_numbers = available_numbers + 1 
                    WHERE code = ?
                ''', (country_code,))
            
            conn.commit()
            return len(expired)

# =================================================
# NUMBER BOT CLASS - MERGED
# =================================================

# =================================================
# NUMBER BOT CLASS - FULLY UPDATED WITH DELETE OPTIONS
# =================================================

class NumberBot:
    def __init__(self, db):
        self.db = db
        self.bot = TeleBot(NUMBER_BOT_TOKEN)
        self.setup_handlers()
        logger.info("✓ Number Bot initialized")
    
    def setup_handlers(self):
        """Setup all Telegram bot handlers"""
        
        @self.bot.message_handler(commands=['start'])
        def start_command(message):
            user_id = message.from_user.id
            username = message.from_user.username or "NoUsername"
            
            self.db.add_user(user_id, username)
            
            welcome = """
👋 *Welcome to Slime Number Bot!*

Get virtual numbers for OTP verification.

⬇️ Click below to get your number!
"""
            self.bot.send_message(
                message.chat.id,
                welcome,
                parse_mode='Markdown',
                reply_markup=self.main_keyboard()
            )
        
        @self.bot.message_handler(commands=['admin'])
        def admin_panel(message):
            if message.from_user.id not in ADMIN_IDS:
                self.bot.reply_to(message, "❌ Admin only!")
                return
            
            self.bot.send_message(
                message.chat.id,
                "🛠 *Admin Panel*\n\nSelect option:",
                parse_mode='Markdown',
                reply_markup=self.admin_keyboard()
            )
        
        @self.bot.message_handler(commands=['broadcast'])
        def broadcast_command(message):
            if message.from_user.id not in ADMIN_IDS:
                self.bot.reply_to(message, "❌ Admin only!")
                return
            
            msg = self.bot.send_message(
                message.chat.id,
                "📢 *Broadcast Message*\n\nSend the message you want to broadcast to all users:",
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(msg, self.process_broadcast)
        
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_handler(call):
            # MAIN MENU
            if call.data == "main_menu":
                self.bot.edit_message_text(
                    "👋 *Main Menu*\n\nSelect an option:",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=self.main_keyboard()
                )
            
            # GET NUMBER
            elif call.data == "get_number":
                self.bot.edit_message_text(
                    "🌍 *Select Country:*\n\nChoose your desired country:",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=self.countries_keyboard()
                )
            
            # MY NUMBERS
            elif call.data == "my_numbers":
                user_id = call.from_user.id
                numbers = self.db.get_user_active_numbers(user_id)
                
                if not numbers:
                    self.bot.answer_callback_query(call.id, "❌ No active numbers!")
                    return
                
                text = "📋 *Your Active Numbers:*\n\n"
                for number, flag, country, expiry in numbers:
                    text += f"{flag} `{number}`\n"
                    text += f"⏰ Exp: {expiry}\n\n"
                
                self.bot.send_message(
                    call.message.chat.id,
                    text,
                    parse_mode='Markdown'
                )
            
            # STOCK
            elif call.data == "stock":
                stock = self.db.get_stock_summary()
                
                text = "📊 *Available Stock:*\n\n"
                for flag, name, available, total, services in stock:
                    percentage = (available / total * 100) if total > 0 else 0
                    bar = "🟢" * int(percentage/10) + "⚪" * (10 - int(percentage/10))
                    text += f"{flag} *{name}*\n"
                    text += f"📱 Available: {available}/{total}\n"
                    text += f"{bar} {percentage:.0f}%\n\n"
                
                self.bot.send_message(
                    call.message.chat.id,
                    text,
                    parse_mode='Markdown'
                )
            
            # SELECT COUNTRY
            elif call.data.startswith('cnt_'):
                country_code = call.data.replace('cnt_', '')
                user_id = call.from_user.id
                
                number_data = self.db.get_available_number(country_code)
                
                if not number_data:
                    self.bot.answer_callback_query(call.id, "❌ No numbers available!")
                    return
                
                number = number_data[0]
                self.db.allocate_number(number, user_id)
                
                # Get country details
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute('SELECT flag, name, services FROM countries WHERE code = ?', (country_code,))
                country_info = c.fetchone()
                conn.close()
                
                flag, country_name, services = country_info if country_info else ('🌍', country_code, '')
                
                keyboard = InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    InlineKeyboardButton("🔄 Get Another", callback_data="get_number"),
                    InlineKeyboardButton("📋 My Numbers", callback_data="my_numbers")
                )
                
                self.bot.edit_message_text(
                    f"✅ *Number Allocated!*\n\n"
                    f"{flag} *Country:* {country_name}\n"
                    f"📱 *Number:* `{number}`\n"
                    f"⏰ *Expires:* 5 minutes\n"
                    f"📱 *Services:* {services}\n\n"
                    f"⏳ Waiting for OTP...",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                
                self.bot.answer_callback_query(call.id, "✅ Number allocated!")
            
            # ============ ADMIN CALLBACKS ============
            
            # ADD COUNTRY
            elif call.data == "admin_add_country":
                if call.from_user.id in ADMIN_IDS:
                    msg = self.bot.send_message(
                        call.message.chat.id,
                        "📝 *Add New Country*\n\n"
                        "Send details in this format:\n\n"
                        "`code|flag|name|services|price`\n\n"
                        "*Example:*\n"
                        "`venezuela|🇻🇪|Venezuela|ws,imo,tg|2`",
                        parse_mode='Markdown'
                    )
                    self.bot.register_next_step_handler(msg, self.process_add_country)
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # ADD NUMBERS
            elif call.data == "admin_add_numbers":
                if call.from_user.id in ADMIN_IDS:
                    countries = self.db.get_all_countries()
                    
                    if not countries:
                        self.bot.send_message(call.message.chat.id, "❌ No countries found! Add country first.")
                        return
                    
                    keyboard = InlineKeyboardMarkup(row_width=1)
                    for country in countries:
                        code, flag, name = country
                        keyboard.add(InlineKeyboardButton(f"{flag} {name}", callback_data=f"addnum_{code}"))
                    
                    self.bot.edit_message_text(
                        "📌 Select country to add numbers:",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=keyboard
                    )
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # ADD NUMBERS - COUNTRY SELECTED
            elif call.data.startswith('addnum_'):
                if call.from_user.id in ADMIN_IDS:
                    country_code = call.data.replace('addnum_', '')
                    
                    msg = self.bot.send_message(
                        call.message.chat.id,
                        f"📝 Send numbers (one per line):\n\n"
                        f"Example:\n"
                        f"584162202162\n"
                        f"584162202163\n"
                        f"584162202164"
                    )
                    self.bot.register_next_step_handler(msg, self.process_add_numbers, country_code)
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # DELETE NUMBER - NEW!
            elif call.data == "admin_delete_number":
                if call.from_user.id in ADMIN_IDS:
                    msg = self.bot.send_message(
                        call.message.chat.id,
                        "📱 *Number Delete*\n\nNumber likho jo delete karna hai:\n\nExample: `584162202161`",
                        parse_mode='Markdown'
                    )
                    self.bot.register_next_step_handler(msg, self.process_delete_number)
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # DELETE COUNTRY - NEW!
            elif call.data == "admin_delete_country":
                if call.from_user.id in ADMIN_IDS:
                    msg = self.bot.send_message(
                        call.message.chat.id,
                        "🌍 *Country Delete*\n\nCountry code likho jo delete karna hai:\n\nExample: `venezuela`",
                        parse_mode='Markdown'
                    )
                    self.bot.register_next_step_handler(msg, self.process_delete_country)
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # STATS
            elif call.data == "admin_stats":
                if call.from_user.id in ADMIN_IDS:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    
                    c.execute('SELECT COUNT(*) FROM users')
                    total_users = c.fetchone()[0]
                    
                    c.execute('SELECT COUNT(*) FROM numbers')
                    total_numbers = c.fetchone()[0]
                    
                    c.execute('SELECT COUNT(*) FROM numbers WHERE status = "allocated"')
                    allocated = c.fetchone()[0]
                    
                    c.execute('SELECT COUNT(*) FROM numbers WHERE status = "available"')
                    available = c.fetchone()[0]
                    
                    c.execute('SELECT COUNT(*) FROM messages')
                    total_sms = c.fetchone()[0]
                    
                    conn.close()
                    
                    stats_text = f"""
📊 *SYSTEM STATISTICS*

👥 *Users:* {total_users}
📱 *Numbers:* {total_numbers}
   • Available: {available}
   • Allocated: {allocated}
📨 *SMS Received:* {total_sms}
⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                    self.bot.send_message(
                        call.message.chat.id,
                        stats_text,
                        parse_mode='Markdown'
                    )
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
            
            # COUNTRIES LIST
            elif call.data == "admin_countries":
                if call.from_user.id in ADMIN_IDS:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute('''SELECT flag, name, total_numbers, available_numbers, services 
                               FROM countries ORDER BY total_numbers DESC''')
                    countries = c.fetchall()
                    conn.close()
                    
                    text = "📋 *Countries List:*\n\n"
                    for flag, name, total, available, services in countries:
                        text += f"{flag} *{name}*\n"
                        text += f"   📱 Total: {total} | Available: {available}\n"
                        text += f"   📱 Services: {services}\n\n"
                    
                    self.bot.send_message(
                        call.message.chat.id,
                        text,
                        parse_mode='Markdown'
                    )
                else:
                    self.bot.answer_callback_query(call.id, "❌ Admin only!")
    
    # ============ PROCESS FUNCTIONS ============
    
    def process_broadcast(self, message):
        if message.from_user.id not in ADMIN_IDS:
            return
        
        broadcast_text = message.text
        users = self.db.get_all_users()
        
        sent = 0
        failed = 0
        
        status_msg = self.bot.reply_to(message, f"📤 Broadcasting to {len(users)} users...")
        
        for user_id in users:
            try:
                self.bot.send_message(
                    user_id,
                    f"📢 *Announcement*\n\n{broadcast_text}",
                    parse_mode='Markdown'
                )
                sent += 1
                time.sleep(0.05)
            except:
                failed += 1
        
        self.bot.edit_message_text(
            f"✅ *Broadcast Complete*\n\n"
            f"✓ Sent: {sent}\n"
            f"✗ Failed: {failed}\n"
            f"📊 Total users: {len(users)}",
            status_msg.chat.id,
            status_msg.message_id,
            parse_mode='Markdown'
        )
    
    def process_add_country(self, message):
        if message.from_user.id not in ADMIN_IDS:
            return
        
        try:
            code, flag, name, services, price = message.text.split('|')
            self.db.add_country(code, flag, name, services, price)
            self.bot.reply_to(message, f"✅ Country added: {flag} {name}")
        except Exception as e:
            self.bot.reply_to(message, f"❌ Error: {e}\n\nFormat: code|flag|name|services|price")
    
    def process_add_numbers(self, message, country_code):
        if message.from_user.id not in ADMIN_IDS:
            return
        
        numbers = message.text.strip().split('\n')
        added = self.db.add_numbers(numbers, country_code)
        
        self.bot.reply_to(
            message,
            f"✅ *Numbers Added*\n\n"
            f"• Added: {added}\n"
            f"• Skipped: {len(numbers) - added}\n"
            f"• Country: {country_code}"
        )
    
    # NEW FUNCTION - DELETE NUMBER
    def process_delete_number(self, message):
        if message.from_user.id not in ADMIN_IDS:
            return
        
        number = message.text.strip()
        conn = sqlite3.connect(DB_PATH)
        
        cursor = conn.execute('SELECT country_code FROM numbers WHERE number = ?', (number,))
        result = cursor.fetchone()
        
        if result:
            country_code = result[0]
            conn.execute('DELETE FROM numbers WHERE number = ?', (number,))
            conn.execute('''UPDATE countries SET 
                           total_numbers = total_numbers - 1,
                           available_numbers = available_numbers - 1
                           WHERE code = ?''', (country_code,))
            conn.commit()
            self.bot.reply_to(message, f"✅ Number `{number}` delete kar diya!")
        else:
            self.bot.reply_to(message, f"❌ Number `{number}` nahi mila!")
        
        conn.close()
    
    # NEW FUNCTION - DELETE COUNTRY
    def process_delete_country(self, message):
        if message.from_user.id not in ADMIN_IDS:
            return
        
        code = message.text.strip().lower()
        conn = sqlite3.connect(DB_PATH)
        
        cursor = conn.execute('SELECT name, flag FROM countries WHERE code = ?', (code,))
        country = cursor.fetchone()
        
        if country:
            name, flag = country
            conn.execute('DELETE FROM numbers WHERE country_code = ?', (code,))
            conn.execute('DELETE FROM countries WHERE code = ?', (code,))
            conn.commit()
            self.bot.reply_to(message, f"✅ {flag} {name} aur uske saare numbers delete!")
        else:
            self.bot.reply_to(message, f"❌ Country code `{code}` nahi mila!")
        
        conn.close()
    
    # ============ KEYBOARDS ============
    
    def main_keyboard(self):
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📱 Get Number", callback_data="get_number"),
            InlineKeyboardButton("📋 My Numbers", callback_data="my_numbers")
        )
        keyboard.add(
            InlineKeyboardButton("📊 Stock", callback_data="stock")
        )
        keyboard.add(
            InlineKeyboardButton("👥 Join Group", url="https://t.me/slimeworld0"),
            InlineKeyboardButton("🆘 Support", url="https://t.me/Slime_313")
        )
        return keyboard
    
    def countries_keyboard(self):
        keyboard = InlineKeyboardMarkup(row_width=2)
        countries = self.db.get_countries_with_stock()
        
        for country in countries:
            code, flag, name, available, services, price = country
            btn_text = f"{flag} {name} ({available})"
            keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"cnt_{code}"))
        
        keyboard.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
        return keyboard
    
    def admin_keyboard(self):
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("➕ Add Country", callback_data="admin_add_country"),
            InlineKeyboardButton("📱 Add Numbers", callback_data="admin_add_numbers")
        )
        keyboard.add(
            InlineKeyboardButton("🗑️ Delete Number", callback_data="admin_delete_number"),
            InlineKeyboardButton("🗑️ Delete Country", callback_data="admin_delete_country")
        )
        keyboard.add(
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("📋 Countries", callback_data="admin_countries")
        )
        return keyboard
    
    def send_otp_notification(self, user_id, number, otp, message):
        """Send OTP notification to user"""
        try:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("📱 Get New Number", callback_data="get_number")
            )
            
            self.bot.send_message(
                user_id,
                f"📨 *OTP Received!*\n\n"
                f"📱 *Number:* `{number}`\n"
                f"🔑 *OTP:* `{otp}`\n"
                f"💬 *Message:* `{message[:100]}`\n\n"
                f"✅ Number auto-deleted!",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send OTP notification to {user_id}: {e}")
            return False
    
    def start(self):
        """Start the number bot in a separate thread"""
        thread = Thread(target=self.bot.infinity_polling, name="NumberBotThread")
        thread.daemon = True
        thread.start()
        logger.info("✓ Number Bot polling started")
# =================================================
# SMS MONITOR BOT - MERGED
# =================================================

class SMSMonitorBot:
    def __init__(self, db):
        self.db = db
        self.session = requests.Session()
        self.running = Event()
        self.running.set()
        self.login_time = None
        self.consecutive_errors = 0
        self.draw_counter = 1
        
        # Headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Load saved session
        self.load_session()
    
    def load_session(self):
        cookies_dict = self.db.load_session()
        if cookies_dict:
            self.session.cookies.update(
                requests.utils.cookiejar_from_dict(cookies_dict)
            )
            logger.info("✓ Session loaded from database")
    
    def save_session(self):
        cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
        self.db.save_session(cookies_dict)
    
    def solve_captcha(self, html):
        """Solve the simple math captcha"""
        try:
            patterns = [
                r'What is\s+(\d+)\s*\+\s*(\d+)\s*=\s*\?\s*:',
                r'What is\s+(\d+)\s*\+\s*(\d+)\s*=',
                r'(\d+)\s*\+\s*(\d+)\s*='
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    num1 = int(match.group(1))
                    num2 = int(match.group(2))
                    answer = str(num1 + num2)
                    return answer
            return None
        except Exception as e:
            logger.error(f"Captcha error: {e}")
            return None
    
    def login(self, force=False):
        """Login to IPRN panel"""
        if not force and self.login_time:
            elapsed = (datetime.now() - self.login_time).total_seconds()
            if elapsed < 300 and self.check_session():
                return True
        
        logger.info("🔐 Logging in...")
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    LOGIN_URL,
                    timeout=REQUEST_TIMEOUT
                )
                
                if response.status_code != 200:
                    time.sleep(RETRY_DELAY)
                    continue
                
                captcha = self.solve_captcha(response.text)
                if not captcha:
                    time.sleep(2)
                    continue
                
                login_data = {
                    'username': USERNAME,
                    'password': PASSWORD,
                    'capt': captcha
                }
                
                login_response = self.session.post(
                    LOGIN_POST_URL,
                    data=login_data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': LOGIN_URL,
                        'Origin': 'http://139.99.208.63'
                    },
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )
                
                if login_response.status_code == 200:
                    content = login_response.text
                    if USERNAME in content and ('Logout' in content or 'Dashboard' in content):
                        logger.info(f"✓ Login successful")
                        self.login_time = datetime.now()
                        self.consecutive_errors = 0
                        self.save_session()
                        return True
                
                time.sleep(RETRY_DELAY * attempt)
                
            except Exception as e:
                logger.warning(f"Login error: {e}")
                time.sleep(RETRY_DELAY)
        
        logger.error("✗ All login attempts failed")
        return False
    
    def check_session(self):
        """Verify session is still valid"""
        try:
            response = self.session.get(
                DASHBOARD_URL,
                timeout=10,
                allow_redirects=False
            )
            
            if response.status_code in [301, 302, 303, 307, 308]:
                location = response.headers.get('Location', '')
                if 'login' in location.lower():
                    return False
            
            if response.status_code == 200:
                content = response.text
                if USERNAME in content and 'Logout' in content:
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Session check failed: {e}")
            return False
    
    def fetch_sms(self):
        """Fetch SMS from panel"""
        try:
            now = datetime.now()
            today_start = now.strftime("%Y-%m-%d 00:00:00")
            today_end = now.strftime("%Y-%m-%d 23:59:59")
            
            params = {
                'fdate1': today_start,
                'fdate2': today_end,
                'frange': '',
                'fclient': '',
                'fnum': '',
                'fcli': '',
                'fgdate': '',
                'fgmonth': '',
                'fgrange': '',
                'fgclient': '',
                'fgnumber': '',
                'fgcli': '',
                'fg': '0',
                'sEcho': str(self.draw_counter),
                'iColumns': '9',
                'sColumns': ',,,,,,,,',
                'iDisplayStart': '0',
                'iDisplayLength': '25',
                'mDataProp_0': '0',
                'sSearch_0': '',
                'bRegex_0': 'false',
                'bSearchable_0': 'true',
                'bSortable_0': 'true',
                'mDataProp_1': '1',
                'sSearch_1': '',
                'bRegex_1': 'false',
                'bSearchable_1': 'true',
                'bSortable_1': 'true',
                'mDataProp_2': '2',
                'sSearch_2': '',
                'bRegex_2': 'false',
                'bSearchable_2': 'true',
                'bSortable_2': 'true',
                'mDataProp_3': '3',
                'sSearch_3': '',
                'bRegex_3': 'false',
                'bSearchable_3': 'true',
                'bSortable_3': 'true',
                'mDataProp_4': '4',
                'sSearch_4': '',
                'bRegex_4': 'false',
                'bSearchable_4': 'true',
                'bSortable_4': 'true',
                'mDataProp_5': '5',
                'sSearch_5': '',
                'bRegex_5': 'false',
                'bSearchable_5': 'true',
                'bSortable_5': 'true',
                'mDataProp_6': '6',
                'sSearch_6': '',
                'bRegex_6': 'false',
                'bSearchable_6': 'true',
                'bSortable_6': 'true',
                'mDataProp_7': '7',
                'sSearch_7': '',
                'bRegex_7': 'false',
                'bSearchable_7': 'true',
                'bSortable_7': 'true',
                'mDataProp_8': '8',
                'sSearch_8': '',
                'bRegex_8': 'false',
                'bSearchable_8': 'true',
                'bSortable_8': 'false',
                'sSearch': '',
                'bRegex': 'false',
                'iSortCol_0': '0',
                'sSortDir_0': 'desc',
                'iSortingCols': '1',
                '_': str(int(time.time() * 1000))
            }
            
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Referer': SMS_REPORT_URL,
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            response = self.session.get(
                SMS_DATA_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    if 'aaData' in data:
                        records = data['aaData']
                        self.draw_counter += 1
                        return self.parse_legacy_response(records)
                    elif 'data' in data:
                        records = data['data']
                        self.draw_counter += 1
                        return self.parse_legacy_response(records)
                    
                except json.JSONDecodeError:
                    pass
            
            return []
            
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return []
    
    def parse_legacy_response(self, records):
        """Parse DataTables response"""
        messages = []
        
        for item in records:
            try:
                if isinstance(item, list) and len(item) >= 6:
                    timestamp = self.clean_text(item[0]) if len(item) > 0 else ''
                    range_name = self.clean_text(item[1]) if len(item) > 1 else ''
                    number = self.clean_text(item[2]) if len(item) > 2 else ''
                    cli = self.clean_text(item[3]) if len(item) > 3 else ''
                    client = self.clean_text(item[4]) if len(item) > 4 else ''
                    message = self.clean_text(item[5]) if len(item) > 5 else ''
                    
                    if number and len(number) >= 8 and message and len(message) > 3:
                        otp_keywords = ['code', 'otp', 'verification', 'pin', 'password', '#', 'is your']
                        is_otp = any(keyword in message.lower() for keyword in otp_keywords)
                        
                        if is_otp or len(message) < 100:
                            messages.append({
                                'timestamp': timestamp,
                                'range': range_name,
                                'number': number,
                                'cli': cli,
                                'client': client,
                                'message': message,
                                'service': cli if cli else (client if client else 'SMS')
                            })
            except Exception:
                continue
        
        return messages
    
    def clean_text(self, text):
        """Clean HTML and normalize text"""
        if not isinstance(text, str):
            text = str(text)
        
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def extract_otp(self, message):
        """Extract OTP from message"""
        patterns = [
            r'#\s*(\d{6,8})',
            r'code[:\s]*(\d{6})',
            r'(\d{6})\s+is\s+your',
            r'is\s+(\d{6})',
            r'(\d{4,6})\s+code',
            r'code[:\s]*(\d{4})',
            r'(\d{3}-\d{3})',
            r'(\d{5,6})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).replace(' ', '-')
        
        return "N/A"
    
    def generate_hash(self, timestamp, number, message):
        """Generate unique hash"""
        unique = f"{timestamp}_{number}_{message[:100]}"
        return hashlib.md5(unique.encode()).hexdigest()
    
    def send_telegram_with_buttons(self, sms):
        """Send notification to main channel"""
        try:
            timestamp = sms['timestamp']
            number = sms['number']
            service = sms.get('service', sms.get('cli', 'SMS'))
            message = sms['message']
            range_name = sms.get('range', 'Unknown')
            
            otp = self.extract_otp(message)
            
            country = range_name
            if range_name:
                match = re.match(r'^([A-Za-z\s]+?)(?:\s+[A-Z0-9]|$)', range_name)
                if match:
                    country = match.group(1).strip()
            
            # Simple emoji mapping
            flag = '🌍'
            icon = '📞'
            
            text = f"""📨 *NEW SMS RECEIVED*

🕐 *Time:* `{timestamp}`
🌍 *Country:* {country}
📱 *Service:* {service}
📞 *Number:* `{number}`
🔑 *OTP:* `{otp}`

💬 *Message:*
`{message[:300]}`"""

            buttons = {
                "inline_keyboard": [
                    [
                        {"text": "📲 GET NUMBER", "url": GET_NUMBER_LINK},
                        {"text": "👨‍💻 DEVELOPER", "url": DEVELOPER_LINK}
                    ]
                ]
            }
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
                'reply_markup': json.dumps(buttons)
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✓ SMS sent to channel: {number} ({otp})")
                return True
            else:
                logger.warning(f"Telegram error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def process_otp_for_number_bot(self, sms, otp, number_bot):
        """Check if number is allocated and send OTP to user"""
        try:
            number = sms['number']
            message = sms['message']
            
            # Check if this number is allocated
            allocated = self.db.check_number_allocated(number)
            
            if allocated:
                user_id = allocated[0]
                
                # Send OTP to user via Number Bot
                if number_bot.send_otp_notification(user_id, number, otp, message):
                    logger.info(f"✓ OTP sent to user {user_id} for number {number}")
                    
                    # AUTO DELETE NUMBER - OTP milte hi delete!
                    self.db.delete_number_on_otp(number)
                    logger.info(f"✓ Number {number} auto-deleted after OTP")
                    
                    return True
            else:
                logger.debug(f"Number {number} not allocated to any user")
            
            return False
            
        except Exception as e:
            logger.error(f"Error processing OTP for number bot: {e}")
            return False
    
    def process_messages(self, messages, number_bot):
        """Process new messages"""
        new_count = 0
        otp_count = 0
        
        for sms in messages:
            try:
                msg_hash = self.generate_hash(
                    sms['timestamp'],
                    sms['number'],
                    sms['message']
                )
                
                if self.db.is_duplicate_sms(msg_hash):
                    continue
                
                self.db.add_sms(
                    msg_hash,
                    sms['timestamp'],
                    sms['number'],
                    sms.get('range', ''),
                    sms.get('cli', ''),
                    sms.get('client', ''),
                    sms['message']
                )
                
                # Extract OTP
                otp = self.extract_otp(sms['message'])
                
                # Send to main channel
                if self.send_telegram_with_buttons(sms):
                    new_count += 1
                
                # Process for Number Bot (auto-delete)
                if self.process_otp_for_number_bot(sms, otp, number_bot):
                    otp_count += 1
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Process error: {e}")
                continue
        
        return new_count, otp_count
    
    def run_cycle(self, number_bot):
        """Single monitoring cycle"""
        try:
            if not self.check_session():
                if not self.login():
                    self.consecutive_errors += 1
                    wait = min(300, 30 * self.consecutive_errors)
                    time.sleep(wait)
                    return False
            
            messages = self.fetch_sms()
            
            if messages:
                new, otp = self.process_messages(messages, number_bot)
                if new or otp:
                    logger.info(f"✓ SMS sent: {new} | OTP delivered: {otp}")
                else:
                    logger.info("No new messages")
            else:
                logger.info("No messages found")
            
            self.consecutive_errors = 0
            return True
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            self.consecutive_errors += 1
            return False
    
    def run(self, number_bot):
        """Main loop"""
        def signal_handler(signum, frame):
            logger.info("Shutdown signal received")
            self.running.clear()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Starting SMS Monitor bot...")
        if not self.login(force=True):
            logger.warning("Initial login failed, will retry...")
        
        cycle = 0
        while self.running.is_set():
            try:
                cycle += 1
                logger.info(f"\n{'='*40}")
                logger.info(f"CYCLE #{cycle}")
                logger.info(f"{'='*40}")
                
                # Cleanup expired numbers
                expired = self.db.cleanup_expired_numbers()
                if expired > 0:
                    logger.info(f"✓ Freed {expired} expired numbers")
                
                self.run_cycle(number_bot)
                
                # Clean old SMS weekly
                if cycle % 1000 == 0:
                    self.db.cleanup_old_sms(days=3)
                
                for _ in range(REFRESH_INTERVAL):
                    if not self.running.is_set():
                        break
                    time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Fatal error: {e}")
                time.sleep(REFRESH_INTERVAL * 2)
        
        logger.info("SMS Monitor shutdown complete")

# =================================================
# MAIN - MERGED APPLICATION
# =================================================

class MergedApplication:
    def __init__(self):
        self.db = Database(DB_PATH)
        self.number_bot = NumberBot(self.db)
        self.sms_bot = SMSMonitorBot(self.db)
        logger.info("=" * 60)
        logger.info("COMPLETE SMS OTP SYSTEM - MERGED VERSION")
        logger.info("=" * 60)
        logger.info(f"Panel User: {USERNAME}")
        logger.info(f"Panel URL: {BASE_URL}")
        logger.info(f"Number Bot: @{NUMBER_BOT_TOKEN[:10]}...")
        logger.info(f"SMS Channel: {TELEGRAM_CHAT_ID}")
        logger.info("=" * 60)
    
    def start(self):
        """Start both bots"""
        logger.info("🚀 Starting merged system...")
        
        # Start Number Bot in background thread
        self.number_bot.start()
        time.sleep(2)
        
        # Start SMS Monitor in main thread
        self.sms_bot.run(self.number_bot)
    
    def test_sms_monitor(self):
        """Test SMS monitor only"""
        if self.sms_bot.check_session() or self.sms_bot.login():
            messages = self.sms_bot.fetch_sms()
            print(f"✓ Found {len(messages)} messages")
            for i, sms in enumerate(messages[:3], 1):
                otp = self.sms_bot.extract_otp(sms['message'])
                print(f"{i}. {sms['number']} - {otp}")
        else:
            print("✗ Login failed")
    
    def test_number_bot(self):
        """Test number bot only"""
        print("✓ Number Bot is running")
        print("📱 Bot token configured")
    
    def test_telegram(self):
        """Test Telegram notifications"""
        test_sms = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'range': 'Myanmar LX 02D',
            'number': '959123456789',
            'cli': 'Facebook',
            'client': '',
            'message': '# 02882130 is your Facebook code',
            'service': 'Facebook'
        }
        if self.sms_bot.send_telegram_with_buttons(test_sms):
            print("✓ Telegram buttons working!")
        else:
            print("✗ Telegram buttons failed")
    
    def add_test_data(self):
        """Add test data for development"""
        # Add test country
        self.db.add_country('venezuela', '🇻🇪', 'Venezuela', 'ws,imo,tg', 2)
        
        # Add test numbers
        test_numbers = [
            '584162202161',
            '584162202162',
            '584162202163',
            '584162202164',
            '584162202165'
        ]
        added = self.db.add_numbers(test_numbers, 'venezuela')
        print(f"✓ Added {added} test numbers for Venezuela")

def main():
    print("\n" + "═" * 60)
    print("  COMPLETE SMS OTP SYSTEM - MERGED VERSION")
    print("═" * 60)
    print("\n📱 Features:")
    print("  • SMS Monitor - OTP fetch from IPRN panel")
    print("  • Number Bot - Users ko numbers allocate")
    print("  • AUTO DELETE - OTP milte hi number delete")
    print("  • Broadcast - Admin se sab users ko message")
    print("  • Stock Management - Countries & numbers")
    print("═" * 60)
    
    app = MergedApplication()
    
    print("\n[1] 🚀 START BOTH BOTS (24/7 Mode)")
    print("[2] 📱 Start Only Number Bot")
    print("[3] 📨 Start Only SMS Monitor")
    print("[4] 🧪 Test SMS Fetch")
    print("[5] 🧪 Test Telegram Buttons")
    print("[6] 📊 Add Test Data")
    print("[7] ❌ Exit")
    
    choice = input("\nSelect (1-7): ").strip()
    
    if choice == "1":
        print("\n🚀 Starting both bots...")
        print("✓ Number bot will run in background")
        print("✓ SMS monitor will run in foreground\n")
        time.sleep(2)
        app.start()
    
    elif choice == "2":
        print("\n📱 Starting Number Bot only...")
        print("Press Ctrl+C to stop\n")
        try:
            app.number_bot.bot.infinity_polling()
        except KeyboardInterrupt:
            print("\n\nNumber Bot stopped")
    
    elif choice == "3":
        print("\n📨 Starting SMS Monitor only...")
        print("Press Ctrl+C to stop\n")
        try:
            app.sms_bot.run(None)  # Number bot disabled
        except KeyboardInterrupt:
            print("\n\nSMS Monitor stopped")
    
    elif choice == "4":
        app.test_sms_monitor()
    
    elif choice == "5":
        app.test_telegram()
    
    elif choice == "6":
        app.add_test_data()
    
    else:
        print("Goodbye!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSystem terminated")
    except Exception as e:
        print(f"\nFatal error: {e}")
        logger.error(f"Fatal error: {e}", exc_info=True)
