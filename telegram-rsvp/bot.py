import os
import sqlite3
import threading
import secrets
import string
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import telebot
from telebot.types import Message

import config

# Initialize Flask
app = Flask(__name__)
# Configure CORS
if config.ALLOWED_ORIGINS == "*":
    CORS(app)
else:
    CORS(app, origins=config.ALLOWED_ORIGINS)

# Rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "10 per hour"],
    storage_uri="memory://"
)

# Initialize Telebot
bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML")

# Database setup
def get_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS sites (
            site_id TEXT PRIMARY KEY,
            site_key TEXT,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS telegram_users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT
        );
        CREATE TABLE IF NOT EXISTS site_subscribers (
            chat_id INTEGER,
            site_id TEXT,
            PRIMARY KEY (chat_id, site_id),
            FOREIGN KEY (chat_id) REFERENCES telegram_users(chat_id),
            FOREIGN KEY (site_id) REFERENCES sites(site_id)
        );
        CREATE TABLE IF NOT EXISTS rsvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id TEXT,
            name TEXT,
            guests INTEGER,
            attendance TEXT,
            phone TEXT,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (site_id) REFERENCES sites(site_id)
        );
    ''')
    
    # Автоматическое восстановление сайта bobur-fariza после перезапуска сервера (Render удаляет файлы)
    c.execute("INSERT OR IGNORE INTO telegram_users (chat_id, username) VALUES (?, ?)", (1168487645, 'admin'))
    c.execute("INSERT OR IGNORE INTO sites (site_id, site_key, title) VALUES (?, ?, ?)",
              ('bobur-fariza', 'MuUkm7qK7AS9E9U6', 'Бобур & Фариза'))
    c.execute("INSERT OR IGNORE INTO site_subscribers (site_id, chat_id) VALUES (?, ?)",
              ('bobur-fariza', 1168487645))
              
    conn.commit()
    conn.close()

init_db()

# --- Helper DB Functions ---
def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(query, params)
        res = None
        if fetchone:
            res = c.fetchone()
        elif fetchall:
            res = c.fetchall()
        if commit:
            conn.commit()
            res = c.lastrowid
        return res
    except Exception as e:
        print(f"DB Error: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def generate_key(length=16):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

def is_admin(chat_id):
    return chat_id in config.ADMIN_IDS

# --- Telegram Bot Handlers ---

@bot.message_handler(commands=['start'])
def cmd_start(message: Message):
    # Register user if not exists
    execute_query("INSERT OR IGNORE INTO telegram_users (chat_id, username) VALUES (?, ?)", 
                  (message.chat.id, message.from_user.username), commit=True)
    
    text = (
        "👋 <b>Добро пожаловать в Multi-Site RSVP Бот!</b>\n\n"
        "Чтобы начать получать уведомления (RSVP) с определенного свадебного сайта, "
        "пожалуйста, введите команду:\n"
        "<code>/connect &lt;site_id&gt; &lt;site_key&gt;</code>\n\n"
        "<i>Например: /connect bobur-fariza XyZ123</i>"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['help'])
def cmd_help(message: Message):
    text = (
        "🛠 <b>Доступные команды:</b>\n"
        "/start — Перезапуск бота\n"
        "/connect &lt;id&gt; &lt;key&gt; — Подключиться к сайту\n"
        "/disconnect &lt;id&gt; — Отключиться от сайта\n"
        "/stop — Отключить все уведомления\n"
        "/stats — Статистика по вашим сайтам\n\n"
    )
    if is_admin(message.chat.id):
        text += (
            "👑 <b>Админские команды:</b>\n"
            "/newsite &lt;site_id&gt; &lt;Название&gt; — Создать сайт\n"
            "/removesite &lt;site_id&gt; — Удалить сайт\n"
            "/clearstats &lt;site_id&gt; — Удалить все тестовые заявки\n"
            "/sites — Список всех сайтов\n"
            "/siteinfo &lt;site_id&gt; — Информация о сайте\n"
        )
    bot.reply_to(message, text)

@bot.message_handler(commands=['connect'])
def cmd_connect(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        bot.reply_to(message, "⚠️ Использование: <code>/connect &lt;site_id&gt; &lt;site_key&gt;</code>")
        return
    
    site_id, site_key = args[1], args[2]
    
    # Check if site and key match
    site = execute_query("SELECT * FROM sites WHERE site_id = ? AND site_key = ?", (site_id, site_key), fetchone=True)
    if not site:
        bot.reply_to(message, "❌ Неверный site_id или site_key.")
        return
    
    execute_query("INSERT OR IGNORE INTO telegram_users (chat_id, username) VALUES (?, ?)", 
                  (message.chat.id, message.from_user.username), commit=True)
    
    execute_query("INSERT OR IGNORE INTO site_subscribers (chat_id, site_id) VALUES (?, ?)", 
                  (message.chat.id, site_id), commit=True)
                  
    bot.reply_to(message, f"✅ Вы успешно подключены к сайту <b>{site['title']}</b>!\nТеперь вы будете получать уведомления.")

@bot.message_handler(commands=['disconnect'])
def cmd_disconnect(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(message, "⚠️ Использование: <code>/disconnect &lt;site_id&gt;</code>")
        return
    
    site_id = args[1]
    execute_query("DELETE FROM site_subscribers WHERE chat_id = ? AND site_id = ?", 
                  (message.chat.id, site_id), commit=True)
    bot.reply_to(message, f"🔌 Вы отключены от уведомлений для сайта: {site_id}.")

@bot.message_handler(commands=['stop'])
def cmd_stop(message: Message):
    execute_query("DELETE FROM site_subscribers WHERE chat_id = ?", 
                  (message.chat.id,), commit=True)
    bot.reply_to(message, "🔇 Все уведомления отключены.\nВы больше не будете получать сообщения о новых RSVP.\n\nЕсли захотите возобновить, введите команду:\n<code>/connect &lt;site_id&gt; &lt;site_key&gt;</code>")

@bot.message_handler(commands=['stats'])
def cmd_stats(message: Message):
    # Get user's sites
    subs = execute_query("SELECT site_id FROM site_subscribers WHERE chat_id = ?", (message.chat.id,), fetchall=True)
    if not subs:
        bot.reply_to(message, "У вас нет подключенных сайтов.")
        return
        
    response = "📊 <b>Статистика ваших сайтов:</b>\n\n"
    for sub in subs:
        site_id = sub['site_id']
        site = execute_query("SELECT title FROM sites WHERE site_id = ?", (site_id,), fetchone=True)
        title = site['title'] if site else site_id
        
        total = execute_query("SELECT COUNT(*) as c FROM rsvps WHERE site_id = ?", (site_id,), fetchone=True)['c']
        attending = execute_query("SELECT COUNT(*) as c FROM rsvps WHERE site_id = ? AND attendance = 'yes'", (site_id,), fetchone=True)['c']
        not_attending = total - attending
        
        guests_row = execute_query("SELECT SUM(guests) as s FROM rsvps WHERE site_id = ? AND attendance = 'yes'", (site_id,), fetchone=True)
        guests = guests_row['s'] if guests_row and guests_row['s'] else 0
        
        response += f"💍 <b>{title}</b> ({site_id})\n"
        response += f"Всего заявок: {total}\n"
        response += f"✅ Придут: {attending}\n"
        response += f"❌ Не придут: {not_attending}\n"
        response += f"👥 Всего гостей: {guests}\n\n"
        
    bot.reply_to(message, response)

# Admin commands
@bot.message_handler(commands=['newsite'])
def cmd_newsite(message: Message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Использование: <code>/newsite &lt;site_id&gt; &lt;Название сайта&gt;</code>")
        return
    
    site_id, title = args[1], args[2]
    
    # Check if exists
    if execute_query("SELECT 1 FROM sites WHERE site_id = ?", (site_id,), fetchone=True):
        bot.reply_to(message, "❌ Сайт с таким ID уже существует.")
        return
        
    site_key = generate_key(16)
    execute_query("INSERT INTO sites (site_id, site_key, title) VALUES (?, ?, ?)", 
                  (site_id, site_key, title), commit=True)
                  
    text = (
        f"✅ <b>Сайт успешно создан!</b>\n\n"
        f"<b>ID:</b> <code>{site_id}</code>\n"
        f"<b>Название:</b> {title}\n"
        f"<b>Key:</b> <code>{site_key}</code>\n\n"
        f"Для подключения бота к этому сайту отправьте:\n"
        f"<code>/connect {site_id} {site_key}</code>"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['sites'])
def cmd_sites(message: Message):
    if not is_admin(message.chat.id):
        return
    sites = execute_query("SELECT * FROM sites", fetchall=True)
    if not sites:
        bot.reply_to(message, "Нет зарегистрированных сайтов.")
        return
        
    text = "🌐 <b>Список сайтов:</b>\n\n"
    for s in sites:
        text += f"▪️ <b>{s['title']}</b> (<code>{s['site_id']}</code>)\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['siteinfo'])
def cmd_siteinfo(message: Message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Использование: <code>/siteinfo &lt;site_id&gt;</code>")
        return
        
    site_id = args[1]
    site = execute_query("SELECT * FROM sites WHERE site_id = ?", (site_id,), fetchone=True)
    if not site:
        bot.reply_to(message, "❌ Сайт не найден.")
        return
        
    subs = execute_query("SELECT COUNT(*) as c FROM site_subscribers WHERE site_id = ?", (site_id,), fetchone=True)['c']
    
    text = (
        f"ℹ️ <b>Информация о сайте</b>\n\n"
        f"<b>Название:</b> {site['title']}\n"
        f"<b>ID:</b> <code>{site['site_id']}</code>\n"
        f"<b>Ключ:</b> <code>{site['site_key']}</code>\n"
        f"<b>Создан:</b> {site['created_at']}\n"
        f"<b>Подписчиков (в боте):</b> {subs}"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['removesite'])
def cmd_removesite(message: Message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Использование: <code>/removesite &lt;site_id&gt;</code>")
        return
        
    site_id = args[1]
    execute_query("DELETE FROM sites WHERE site_id = ?", (site_id,), commit=True)
    execute_query("DELETE FROM site_subscribers WHERE site_id = ?", (site_id,), commit=True)
    execute_query("DELETE FROM rsvps WHERE site_id = ?", (site_id,), commit=True)
    bot.reply_to(message, f"✅ Сайт {site_id} и все его данные удалены.")

@bot.message_handler(commands=['clearstats'])
def cmd_clearstats(message: Message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Использование: <code>/clearstats &lt;site_id&gt;</code>")
        return
        
    site_id = args[1]
    execute_query("DELETE FROM rsvps WHERE site_id = ?", (site_id,), commit=True)
    bot.reply_to(message, f"🧹 Все тестовые заявки (RSVP) для сайта {site_id} успешно удалены!\nТеперь статистика обнулена.")


# --- Flask REST API ---

@app.route('/api/v1/rsvp', methods=['POST'])
@limiter.limit("5 per minute")
def handle_rsvp():
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No JSON payload"}), 400
            
        site_id = data.get('site_id')
        site_key = data.get('site_key')
        name = data.get('name')
        guests = data.get('guests', 0)
        attendance = data.get('attendance')
        comment = data.get('comment', '')
        phone = data.get('phone', '')
        
        if not all([site_id, site_key, name, attendance]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
            
        if len(name) > 100 or len(comment) > 500:
            return jsonify({"success": False, "error": "Field lengths exceeded"}), 400
            
        try:
            guests = int(guests)
            if guests < 0 or guests > 50:
                guests = 0
        except:
            guests = 0
            
        if attendance not in ['yes', 'no']:
            return jsonify({"success": False, "error": "Invalid attendance value"}), 400
            
        # Verify credentials
        site = execute_query("SELECT title FROM sites WHERE site_id = ? AND site_key = ?", (site_id, site_key), fetchone=True)
        if not site:
            return jsonify({"success": False, "error": "Invalid site credentials"}), 401
            
        # Save to DB
        execute_query(
            "INSERT INTO rsvps (site_id, name, guests, attendance, phone, comment) VALUES (?, ?, ?, ?, ?, ?)",
            (site_id, name, guests, attendance, phone, comment),
            commit=True
        )
        
        # Send Telegram notifications
        subs = execute_query("SELECT chat_id FROM site_subscribers WHERE site_id = ?", (site_id,), fetchall=True)
        if subs:
            title = site['title']
            att_text = "✅ Присутствие: Да" if attendance == 'yes' else "❌ Присутствие: Нет"
            
            msg = f"💌 <b>НОВЫЙ RSVP</b>\n\n💍 {title}\n\n👤 Имя: {name}\n👥 Гостей: {guests}\n{att_text}\n"
            if comment:
                msg += f"💬 Пожелание: {comment}\n"
            msg += f"\n#{site_id.replace('-', '')}"
            
            for sub in subs:
                try:
                    bot.send_message(sub['chat_id'], msg)
                except Exception as e:
                    print(f"Failed to send to {sub['chat_id']}: {e}")
                    
        return jsonify({"success": True, "message": "RSVP received"})
        
    except Exception as e:
        print(f"Error handling RSVP: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    print("Starting Flask API in background...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("Starting Telegram Bot...")
    bot.infinity_polling()
