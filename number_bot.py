#!/usr/bin/env python3
"""
TELEGRAM NUMBER BOT - INDEPENDENT SCRIPT
Sirf numbers allocate karega, OTP forward nahi karega
SMS Monitor bot OTP forward karega alag se
Author: Senior Python Automation Engineer
"""

import os
import sys
import sqlite3
import json
import time
from datetime import datetime, timedelta
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading

# =================================================
# CONFIGURATION - YAHAN APNI VALUES DALO
# =================================================

BOT_TOKEN = "8569562005:AAEKCUTPL7vm5pEaBIoOeqwME9rPrRUzVwM"  # @BotFather se naya bot banao
ADMIN_IDS = [7520986318]  # Apna Telegram ID

# =================================================
# DATABASE SETUP
# =================================================

DB_PATH = 'number_bot.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  joined_date TEXT,
                  total_numbers INTEGER DEFAULT 0)''')
    
    # Countries table
    c.execute('''CREATE TABLE IF NOT EXISTS countries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE,
                  name TEXT,
                  flag TEXT,
                  services TEXT,
                  price INTEGER DEFAULT 1,
                  total_numbers INTEGER DEFAULT 0,
                  available_numbers INTEGER DEFAULT 0)''')
    
    # Numbers table
    c.execute('''CREATE TABLE IF NOT EXISTS numbers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  number TEXT UNIQUE,
                  country_code TEXT,
                  status TEXT DEFAULT 'available',
                  allocated_to INTEGER,
                  allocated_at TEXT,
                  expiry TEXT,
                  FOREIGN KEY (country_code) REFERENCES countries(code),
                  FOREIGN KEY (allocated_to) REFERENCES users(user_id))''')
    
    # Stats table
    c.execute('''CREATE TABLE IF NOT EXISTS stats
                 (date TEXT PRIMARY KEY,
                  numbers_allocated INTEGER DEFAULT 0,
                  otp_received INTEGER DEFAULT 0)''')
    
    conn.commit()
    conn.close()

init_db()

# =================================================
# TELEGRAM BOT
# =================================================

bot = TeleBot(BOT_TOKEN)

# =================================================
# KEYBOARDS
# =================================================

def main_keyboard():
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

def countries_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT code, flag, name, available_numbers, services, price 
                 FROM countries WHERE available_numbers > 0 ORDER BY name''')
    countries = c.fetchall()
    conn.close()
    
    for country in countries:
        code, flag, name, available, services, price = country
        btn_text = f"{flag} {name} ({available})"
        if services:
            btn_text += f" - {services[:15]}"
        keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"cnt_{code}"))
    
    keyboard.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return keyboard

def admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Add Country", callback_data="admin_add_country"),
        InlineKeyboardButton("📱 Add Numbers", callback_data="admin_add_numbers")
    )
    keyboard.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📋 Countries", callback_data="admin_countries")
    )
    return keyboard

# =================================================
# START COMMAND
# =================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Add user to database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, joined_date) 
                 VALUES (?, ?, ?)''',
              (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    welcome = f"""
👋 *Welcome to Slime Number Bot!*

Get virtual numbers for OTP verification.

⬇️ Click below to get your number!
"""
    
    bot.send_message(
        message.chat.id,
        welcome,
        parse_mode='Markdown',
        reply_markup=main_keyboard()
    )

# =================================================
# ADMIN COMMANDS - COUNTRIES ADD KARO
# =================================================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Admin only!")
        return
    
    bot.send_message(
        message.chat.id,
        "🛠 *Admin Panel*\n\nSelect option:",
        parse_mode='Markdown',
        reply_markup=admin_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_country")
def admin_add_country(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "📝 *Add New Country*\n\n"
        "Send details in this format:\n\n"
        "`code|flag|name|services|price`\n\n"
        "*Example:*\n"
        "`venezuela|🇻🇪|Venezuela|ws,imo,tg|2`",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_add_country)

def process_add_country(message):
    try:
        code, flag, name, services, price = message.text.split('|')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO countries 
                     (code, flag, name, services, price, total_numbers, available_numbers)
                     VALUES (?, ?, ?, ?, ?, 0, 0)''',
                  (code.strip(), flag.strip(), name.strip(), services.strip(), int(price)))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Country added: {flag} {name}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}\n\nFormat: code|flag|name|services|price")

# =================================================
# ADMIN - NUMBERS ADD KARO
# =================================================

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_numbers")
def admin_add_numbers(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Unauthorized!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT code, flag, name FROM countries ORDER BY name')
    countries = c.fetchall()
    conn.close()
    
    if not countries:
        bot.send_message(call.message.chat.id, "❌ No countries found! Add country first.")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for country in countries:
        code, flag, name = country
        keyboard.add(InlineKeyboardButton(f"{flag} {name}", callback_data=f"addnum_{code}"))
    
    bot.edit_message_text(
        "📌 Select country to add numbers:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('addnum_'))
def add_numbers_callback(call):
    country_code = call.data.replace('addnum_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        f"📝 Send numbers (one per line):\n\n"
        f"Example:\n"
        f"584162202162\n"
        f"584162202163\n"
        f"584162202164"
    )
    bot.register_next_step_handler(msg, process_add_numbers, country_code)

def process_add_numbers(message, country_code):
    numbers = message.text.strip().split('\n')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    added = 0
    skipped = 0
    
    for number in numbers:
        number = number.strip()
        if number:
            try:
                c.execute('''INSERT OR IGNORE INTO numbers 
                           (number, country_code, status) 
                           VALUES (?, ?, 'available')''',
                        (number, country_code))
                if c.rowcount > 0:
                    added += 1
                else:
                    skipped += 1
            except:
                skipped += 1
    
    # Update country counts
    c.execute('''UPDATE countries SET 
                 total_numbers = total_numbers + ?,
                 available_numbers = available_numbers + ?
                 WHERE code = ?''', (added, added, country_code))
    
    conn.commit()
    conn.close()
    
    bot.reply_to(
        message,
        f"✅ *Numbers Added*\n\n"
        f"• Added: {added}\n"
        f"• Skipped (duplicate): {skipped}\n"
        f"• Country: {country_code}"
    )

# =================================================
# USER - GET NUMBER
# =================================================

@bot.callback_query_handler(func=lambda call: call.data == "get_number")
def get_number_callback(call):
    bot.edit_message_text(
        "🌍 *Select Country:*\n\nChoose your desired country:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=countries_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('cnt_'))
def select_country_callback(call):
    country_code = call.data.replace('cnt_', '')
    user_id = call.from_user.id
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get available number
    c.execute('''SELECT number FROM numbers 
                 WHERE country_code = ? AND status = 'available' 
                 LIMIT 1''', (country_code,))
    number_data = c.fetchone()
    
    if not number_data:
        bot.answer_callback_query(call.id, "❌ No numbers available!")
        conn.close()
        return
    
    number = number_data[0]
    
    # Allocate number
    now = datetime.now()
    expiry = now + timedelta(minutes=5)
    
    c.execute('''UPDATE numbers SET 
                 status = 'allocated',
                 allocated_to = ?,
                 allocated_at = ?,
                 expiry = ?
                 WHERE number = ?''',
              (user_id, now.strftime("%Y-%m-%d %H:%M:%S"), 
               expiry.strftime("%Y-%m-%d %H:%M:%S"), number))
    
    # Update available count
    c.execute('''UPDATE countries SET available_numbers = available_numbers - 1 
                 WHERE code = ?''', (country_code,))
    
    # Update user stats
    c.execute('''UPDATE users SET total_numbers = total_numbers + 1 
                 WHERE user_id = ?''', (user_id,))
    
    conn.commit()
    
    # Get country details
    c.execute('SELECT flag, name, services FROM countries WHERE code = ?', (country_code,))
    country_info = c.fetchone()
    conn.close()
    
    flag, country_name, services = country_info if country_info else ('🌍', country_code, '')
    
    # Send number to user
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔄 Get Another", callback_data="get_number"),
        InlineKeyboardButton("📋 My Numbers", callback_data="my_numbers")
    )
    
    bot.edit_message_text(
        f"✅ *Number Allocated!*\n\n"
        f"{flag} *Country:* {country_name}\n"
        f"📱 *Number:* `{number}`\n"
        f"⏰ *Expires:* 5 minutes\n"
        f"📱 *Services:* {services}\n\n"
        f"⏳ Waiting for OTP...\n"
        f"📨 OTP will appear in @YourOTPGroup",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    
    bot.answer_callback_query(call.id, "✅ Number allocated!")

# =================================================
# USER - MY NUMBERS
# =================================================

@bot.callback_query_handler(func=lambda call: call.data == "my_numbers")
def my_numbers_callback(call):
    user_id = call.from_user.id
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT n.number, c.flag, c.name, n.expiry 
                 FROM numbers n
                 JOIN countries c ON n.country_code = c.code
                 WHERE n.allocated_to = ? AND n.status = 'allocated'
                 ORDER BY n.allocated_at DESC LIMIT 10''', (user_id,))
    numbers = c.fetchall()
    conn.close()
    
    if not numbers:
        bot.answer_callback_query(call.id, "❌ No active numbers!")
        return
    
    text = "📋 *Your Active Numbers:*\n\n"
    for number, flag, country, expiry in numbers:
        text += f"{flag} `{number}`\n"
        text += f"⏰ Exp: {expiry}\n\n"
    
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='Markdown'
    )

# =================================================
# API ENDPOINT - SMS MONITOR BOT CALL KAREGA
# =================================================

class NumberBotAPI:
    """Yeh functions SMS Monitor bot call karega jab OTP aye"""
    
    @staticmethod
    def otp_received(number, otp, message):
        """
        Jab OTP aye to yeh function call karo
        Yeh number ko auto delete kar dega
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if number is allocated
        c.execute('''SELECT allocated_to FROM numbers 
                     WHERE number = ? AND status = 'allocated' ''', (number,))
        allocated = c.fetchone()
        
        if allocated:
            user_id = allocated[0]
            
            # AUTO DELETE NUMBER - OTP milte hi delete!
            c.execute('DELETE FROM numbers WHERE number = ?', (number,))
            
            # Update country count
            c.execute('''UPDATE countries SET total_numbers = total_numbers - 1 
                         WHERE code = (SELECT country_code FROM numbers WHERE number = ?)''', (number,))
            
            conn.commit()
            
            # Send notification to user
            try:
                bot = TeleBot(BOT_TOKEN)
                bot.send_message(
                    user_id,
                    f"📨 *OTP Received!*\n\n"
                    f"📱 *Number:* `{number}`\n"
                    f"🔑 *OTP:* `{otp}`\n\n"
                    f"✅ Number auto-deleted!",
                    parse_mode='Markdown'
                )
            except:
                pass
            
            print(f"✓ Auto deleted number {number} - OTP sent to {user_id}")
            return True
        
        conn.close()
        return False

# =================================================
# STOCK CHECK
# =================================================

@bot.callback_query_handler(func=lambda call: call.data == "stock")
def stock_callback(call):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT flag, name, available_numbers, total_numbers, services 
                 FROM countries WHERE total_numbers > 0 ORDER BY available_numbers DESC LIMIT 15''')
    countries = c.fetchall()
    conn.close()
    
    text = "📊 *Available Stock:*\n\n"
    for flag, name, available, total, services in countries:
        percentage = (available / total * 100) if total > 0 else 0
        bar = "🟢" * int(percentage/10) + "⚪" * (10 - int(percentage/10))
        text += f"{flag} *{name}*\n"
        text += f"📱 Available: {available}/{total}\n"
        text += f"{bar} {percentage:.0f}%\n\n"
    
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='Markdown'
    )

# =================================================
# MAIN MENU
# =================================================

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def main_menu_callback(call):
    bot.edit_message_text(
        "👋 *Main Menu*\n\nSelect an option:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=main_keyboard()
    )

# =================================================
# START BOT
# =================================================

def start_bot():
    print("🤖 Number Bot Started!")
    print(f"📱 Bot: @{bot.get_me().username}")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    bot.infinity_polling()

if __name__ == "__main__":
    start_bot()
