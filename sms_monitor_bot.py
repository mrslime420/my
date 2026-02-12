#!/usr/bin/env python3
"""
SMS MONITORING BOT - IPRN PANEL EDITION
WITH TELEGRAM BUTTONS - 1000% WORKING
Author: Senior Python Automation Engineer
Version: 7.0.0 - WITH INLINE BUTTONS
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
from threading import Event
import signal
import logging
from logging.handlers import RotatingFileHandler

# =================================================
# CREDENTIALS
# =================================================

USERNAME = "awais1234"
PASSWORD = "awais1234"
TELEGRAM_BOT_TOKEN = "8278099501:AAEO-0bQTAmAbC7_qaYvVjnH-dGZAialSMU"
TELEGRAM_CHAT_ID = "-1003862493586"

# =================================================
# CONFIGURATION
# =================================================

BASE_URL = "http://139.99.208.63/ints/"
LOGIN_URL = urljoin(BASE_URL, "login")
LOGIN_POST_URL = urljoin(BASE_URL, "signin")
DASHBOARD_URL = urljoin(BASE_URL, "agent/SMSDashboard")
SMS_REPORT_URL = urljoin(BASE_URL, "agent/SMSCDRReports")
SMS_DATA_URL = urljoin(BASE_URL, "agent/res/data_smscdr.php")

REFRESH_INTERVAL = 5  # seconds - SAFE MODE
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 10

# =================================================
# BUTTON LINKS - APNE LINKS LAGAO YAHAN
# =================================================

GET_NUMBER_LINK = "https://t.me/slimenumberbot"  # CHANGE KARO
DEVELOPER_LINK = "https://t.me/Slime_313"     # CHANGE KARO

# =================================================
# PATH SETUP
# =================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'sms_data')
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'sms_messages.db')
LOG_FILE = os.path.join(DATA_DIR, 'sms_bot.log')

# =================================================
# LOGGING SETUP
# SMS Monitor bot ke OTP send karne se PEHLE yeh call karo

def notify_number_bot(number, otp, message):
    """Number bot ko batao ke OTP aagaya"""
    try:
        # Number bot ka API function call karo
        from number_bot import NumberBotAPI
        NumberBotAPI.otp_received(number, otp, message)
    except:
        pass

# Jab OTP mile:
if otp != "N/A":
    notify_number_bot(sms['number'], otp, sms['message'])
    # Phir Telegram send karo
    send_telegram(sms)
# =================================================

def setup_logging():
    logger = logging.getLogger('SMSBot')
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
# DATABASE MANAGER
# =================================================

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
            conn.execute('CREATE INDEX IF NOT EXISTS idx_hash ON messages(hash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS session (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    
    def is_duplicate(self, msg_hash):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM messages WHERE hash = ? LIMIT 1',
                (msg_hash,)
            )
            return cursor.fetchone() is not None
    
    def add_message(self, msg_hash, timestamp, number, range_name, cli, client, message):
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
    
    def cleanup_old(self, days=7):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'DELETE FROM messages WHERE datetime(received_at) < datetime("now", "-? days")',
                (days,)
            )
            conn.commit()

# =================================================
# SMS BOT - IPRN PANEL - WITH BUTTONS
# =================================================

class IPRNSMSBot:
    def __init__(self):
        self.session = requests.Session()
        self.db = Database(DB_PATH)
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
        
        logger.info("=" * 60)
        logger.info("SMS MONITORING BOT - WITH TELEGRAM BUTTONS")
        logger.info("=" * 60)
        logger.info(f"User: {USERNAME}")
        logger.info(f"Panel: {BASE_URL}")
        logger.info(f"Refresh: {REFRESH_INTERVAL}s")
        logger.info(f"Get Number Link: {GET_NUMBER_LINK}")
        logger.info(f"Developer Link: {DEVELOPER_LINK}")
        logger.info("=" * 60)
    
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
                    logger.debug(f"Captcha: {num1}+{num2}={answer}")
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
                    logger.warning(f"Login page failed: {response.status_code}")
                    time.sleep(RETRY_DELAY)
                    continue
                
                captcha = self.solve_captcha(response.text)
                if not captcha:
                    logger.warning("No captcha found, retrying...")
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
                        logger.info(f"✓ Login successful (attempt {attempt})")
                        self.login_time = datetime.now()
                        self.consecutive_errors = 0
                        self.save_session()
                        return True
                
                logger.warning(f"Login attempt {attempt} failed")
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
        """EXACT CURL REQUEST - DataTables 1.9 legacy format"""
        try:
            now = datetime.now()
            today_start = now.strftime("%Y-%m-%d 00:00:00")
            today_end = now.strftime("%Y-%m-%d 23:59:59")
            
            # EXACT parameters from curl
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
            
            logger.debug("Fetching SMS...")
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
                        total_records = data.get('iTotalRecords', 0)
                        logger.info(f"✓ Found {len(records)} records (Total: {total_records})")
                        self.draw_counter += 1
                        return self.parse_legacy_response(records)
                    elif 'data' in data:
                        records = data['data']
                        logger.info(f"✓ Found {len(records)} records")
                        self.draw_counter += 1
                        return self.parse_legacy_response(records)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
            
            return []
            
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return []
    
    def parse_legacy_response(self, records):
        """Parse DataTables legacy response format"""
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
            except Exception as e:
                continue
        
        return messages
    
    def clean_text(self, text):
        """Clean HTML and normalize text"""
        if not isinstance(text, str):
            text = str(text)
        
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
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
        """Generate unique hash for deduplication"""
        unique = f"{timestamp}_{number}_{message[:100]}"
        return hashlib.md5(unique.encode()).hexdigest()
    
    def send_telegram_with_buttons(self, sms):
        """
        Send notification to Telegram with 2 INLINE BUTTONS
        ✅ Button 1: Get Number
        ✅ Button 2: Developer
        """
        try:
            timestamp = sms['timestamp']
            number = sms['number']
            service = sms.get('service', sms.get('cli', 'SMS'))
            message = sms['message']
            range_name = sms.get('range', 'Unknown')
            
            # Clean service name
            service = service.replace('&amp;', '&').strip()
            if not service or service == 'Unknown' or service == '':
                service = 'SMS Service'
            
            # Extract OTP
            otp = self.extract_otp(message)
            
            # Extract country from range
            country = range_name
            if range_name:
                match = re.match(r'^([A-Za-z\s]+?)(?:\s+[A-Z0-9]|$)', range_name)
                if match:
                    country = match.group(1).strip()
            
            # Emoji mapping
            country_emoji = {
                'myanmar': '🇲🇲', 'pakistan': '🇵🇰', 'india': '🇮🇳',
                'usa': '🇺🇸', 'uk': '🇬🇧', 'uae': '🇦🇪',
                'saudi': '🇸🇦', 'egypt': '🇪🇬', 'turkey': '🇹🇷',
                'russia': '🇷🇺', 'china': '🇨🇳', 'brazil': '🇧🇷',
                'indonesia': '🇮🇩', 'malaysia': '🇲🇾', 'thailand': '🇹🇭',
                'vietnam': '🇻🇳', 'philippines': '🇵🇭'
            }
            
            service_emoji = {
                'facebook': '📘', 'whatsapp': '📱', 'telegram': '📨',
                'google': '🔍', 'instagram': '📸', 'twitter': '🐦',
                'amazon': '🛒', 'paypal': '💰', 'snapchat': '👻',
                'tiktok': '🎵', 'linkedin': '💼', 'alibaba': '🏭',
                'wechat': '💬', 'viber': '📞', 'imo': '📱'
            }
            
            # Find emojis
            flag = '🌍'
            for key, emoji in country_emoji.items():
                if key in country.lower():
                    flag = emoji
                    break
            
            icon = '📞'
            for key, emoji in service_emoji.items():
                if key in service.lower():
                    icon = emoji
                    break
            
            # ============================================
            # MAIN MESSAGE WITH OTP
            # ============================================
            text = f"""📨 *NEW SMS RECEIVED*

🕐 *Time:* `{timestamp}`
🌍 *Country:* {country} {flag}
📱 *Service:* {icon} {service}
📞 *Number:* `{number}`
🔑 *OTP:* `{otp}`

💬 *Message:*
`{message[:300]}`"""

            # ============================================
            # 2 INLINE BUTTONS - YAHAN APNE LINKS LAGAO
            # ============================================
            buttons = {
                "inline_keyboard": [
                    [
                        {"text": "📲 GET NUMBER", "url": GET_NUMBER_LINK},
                        {"text": "👨‍💻 DEVELOPER", "url": DEVELOPER_LINK}
                    ]
                ]
            }
            
            # Send to Telegram with buttons
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
                'reply_markup': json.dumps(buttons)  # BUTTONS YAHAN ADD HO RAHE HAIN
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✓ Telegram + Buttons: {number} ({otp})")
                return True
            else:
                logger.warning(f"Telegram error: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def process_messages(self, messages):
        """Process new messages with buttons"""
        new_count = 0
        
        for sms in messages:
            try:
                msg_hash = self.generate_hash(
                    sms['timestamp'],
                    sms['number'],
                    sms['message']
                )
                
                if self.db.is_duplicate(msg_hash):
                    continue
                
                self.db.add_message(
                    msg_hash,
                    sms['timestamp'],
                    sms['number'],
                    sms.get('range', ''),
                    sms.get('cli', ''),
                    sms.get('client', ''),
                    sms['message']
                )
                
                # Send with buttons
                if self.send_telegram_with_buttons(sms):
                    new_count += 1
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Process error: {e}")
                continue
        
        return new_count
    
    def run_cycle(self):
        """Single monitoring cycle"""
        try:
            if not self.check_session():
                if not self.login():
                    self.consecutive_errors += 1
                    wait = min(300, 30 * self.consecutive_errors)
                    logger.warning(f"Login failed, waiting {wait}s...")
                    time.sleep(wait)
                    return False
            
            messages = self.fetch_sms()
            
            if messages:
                new = self.process_messages(messages)
                if new:
                    logger.info(f"✓ {new} new notifications sent with buttons")
                else:
                    logger.info("No new messages (duplicates skipped)")
            else:
                logger.info("No messages found")
            
            self.consecutive_errors = 0
            return True
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            self.consecutive_errors += 1
            return False
    
    def run(self):
        """Main loop"""
        def signal_handler(signum, frame):
            logger.info("Shutdown signal received")
            self.running.clear()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Starting bot with Telegram buttons...")
        if not self.login(force=True):
            logger.warning("Initial login failed, will retry...")
        
        cycle = 0
        while self.running.is_set():
            try:
                cycle += 1
                logger.info(f"\n{'='*40}")
                logger.info(f"CYCLE #{cycle} - {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'='*40}")
                
                self.run_cycle()
                
                if cycle % 1000 == 0:
                    self.db.cleanup_old(days=3)
                
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
        
        logger.info("Bot shutdown complete")

# =================================================
# AUTO MODE FOR HOSTING
# =================================================

def auto_mode():
    """For hosting - runs once and exits"""
    print(f"\n[{datetime.now()}] SMS Bot - Auto Mode")
    bot = IPRNSMSBot()
    
    if bot.check_session() or bot.login():
        messages = bot.fetch_sms()
        if messages:
            new = bot.process_messages(messages)
            print(f"[{datetime.now()}] ✓ Sent {new} messages with buttons")
        else:
            print(f"[{datetime.now()}] No messages")
    else:
        print(f"[{datetime.now()}] ✗ Login failed")

# =================================================
# MAIN
# =================================================

def main():
    print("\n" + "═" * 60)
    print("  SMS MONITORING BOT - WITH TELEGRAM BUTTONS")
    print("═" * 60)
    print(f"\n👤 User: {USERNAME}")
    print(f"🌐 Panel: {BASE_URL}")
    print(f"⏱️  Refresh: {REFRESH_INTERVAL}s")
    print(f"📲 Get Number: {GET_NUMBER_LINK}")
    print(f"👨‍💻 Developer: {DEVELOPER_LINK}")
    print("═" * 60)
    
    print("\n[1] Start Monitoring (24/7 Mode)")
    print("[2] Test Login Only")
    print("[3] Test SMS Fetch")
    print("[4] Test Telegram Buttons")
    print("[5] Auto Mode (For Hosting)")
    print("[6] Exit")
    
    choice = input("\nSelect (1-6): ").strip()
    
    if choice == "1":
        bot = IPRNSMSBot()
        bot.run()
    elif choice == "2":
        bot = IPRNSMSBot()
        if bot.login(force=True):
            print("✓ Login successful")
        else:
            print("✗ Login failed")
    elif choice == "3":
        bot = IPRNSMSBot()
        if not bot.check_session():
            bot.login()
        messages = bot.fetch_sms()
        print(f"✓ Found {len(messages)} messages")
        for i, sms in enumerate(messages[:3], 1):
            print(f"\n{i}. {sms['number']} - {bot.extract_otp(sms['message'])}")
    elif choice == "4":
        bot = IPRNSMSBot()
        test_sms = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'range': 'Myanmar LX 02D',
            'number': '959123456789',
            'cli': 'Facebook',
            'client': '',
            'message': '# 02882130 is your Facebook code',
            'service': 'Facebook'
        }
        if bot.send_telegram_with_buttons(test_sms):
            print("✓ Telegram buttons working!")
        else:
            print("✗ Telegram buttons failed")
    elif choice == "5":
        auto_mode()
    else:
        print("Goodbye!")

if __name__ == "__main__":
    try:
        if "--auto" in sys.argv:
            auto_mode()
        else:
            main()
    except KeyboardInterrupt:
        print("\n\nBot terminated")
    except Exception as e:
        print(f"\nFatal error: {e}")
        logger.error(f"Fatal error: {e}", exc_info=True)
