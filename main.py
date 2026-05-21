import random
import sqlite3
import asyncio
import traceback
import logging
import atexit
from datetime import datetime, time, timedelta
from collections import defaultdict
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.constants import ChatType

# =====================================================================
# КОНФИГУРАЦИЯ
# =====================================================================
BOT_TOKEN = "8643635341:AAHLcxbOjtwgQgHS0KvrvMit5cuyu43ra4w"
ADMIN_IDS = [7956317602, 5243173039]

TRIGGER_WORDS = ["привет", "как ты", "салам"]
REPLY_WORDS = ["Привет 👋", "Салам 🤝", "Здорова 😎"]

RANKS = [
    (0, "🌊 Залётный", "🌊"),
    (101, "🔥 Активный", "🔥"),
    (501, "🏠 Местный", "🏠"),
    (1001, "👑 Легенда", "👑"),
    (1501, "⭐ Свой", "⭐")
]

TABLE_MAP = {"shop": "shops", "exch": "exchangers", "vpn": "vpn", "job": "jobs"}

# =====================================================================
# ЛОГИРОВАНИЕ
# =====================================================================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================================================================
# БАЗА ДАННЫХ
# =====================================================================
class Database:
    def __init__(self, db_file="brandovichok.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._init_default()
        self._verify_tables()

    def _create_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, msg_count INTEGER DEFAULT 0,
                first_seen TEXT, vip INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0, reputation INTEGER DEFAULT 0, donations INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS daily_stats (
                user_id INTEGER, date TEXT, msg_count INTEGER DEFAULT 0, PRIMARY KEY (user_id, date))""",
            """CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY, banned_at TEXT, reason TEXT)""",
            """CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT, icon TEXT)""",
            """CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER, ach_name TEXT, earned_at TEXT, PRIMARY KEY (user_id, ach_name))""",
            """CREATE TABLE IF NOT EXISTS shops (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, username TEXT,
                description TEXT, photo TEXT, views INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS exchangers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, username TEXT,
                description TEXT, photo TEXT, views INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS vpn (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, username TEXT,
                description TEXT, photo TEXT, views INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, username TEXT,
                description TEXT, photo TEXT, views INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS info (
                key TEXT PRIMARY KEY, text TEXT, photo TEXT)""",
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT)""",
            """CREATE TABLE IF NOT EXISTS triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT UNIQUE,
                reply_text TEXT, reply_photo TEXT, reply_document TEXT,
                reply_video TEXT, reply_sticker TEXT, reply_voice TEXT, reply_audio TEXT)"""
        ]
        for table_sql in tables:
            try:
                self.cursor.execute(table_sql)
            except Exception as e:
                logger.error(f"❌ Ошибка создания таблицы: {e}")
        self.conn.commit()
        logger.info("✅ Все таблицы созданы")

    def _verify_tables(self):
        expected = ["users", "daily_stats", "banned_users", "achievements", "user_achievements",
                    "shops", "exchangers", "vpn", "jobs", "info", "settings", "triggers"]
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = [r[0] for r in self.cursor.fetchall()]
        missing = [t for t in expected if t not in existing]
        if missing:
            logger.error(f"⚠️ Отсутствуют таблицы: {missing}")
        else:
            logger.info("✅ Все таблицы проверены")

    def _init_default(self):
        self.cursor.execute("INSERT OR IGNORE INTO info (key, text) VALUES ('rules_chat', '📜 Правила чата пока не заданы.')")
        self.cursor.execute("INSERT OR IGNORE INTO info (key, text) VALUES ('rules_bingo', '🎲 Правила бинго пока не заданы.')")
        self.cursor.execute("INSERT OR IGNORE INTO info (key, text) VALUES ('links', '🔗 Полезные ссылки пока не заданы.')")
        self.cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('menu_photo', '')")
        for name, desc, icon in [
            ("Первая кровь", "Одержать первую победу", "🩸"),
            ("Массовик", "Одержать 5 побед", "📢"),
            ("VIP", "Получить VIP статус", "👑"),
            ("Топ донатер", "Проспонсировать 3 игры", "💰")
        ]:
            self.cursor.execute("INSERT OR IGNORE INTO achievements (name, description, icon) VALUES (?, ?, ?)", (name, desc, icon))
        self.conn.commit()

    def is_admin(self, uid): return uid in ADMIN_IDS

    def ensure_user(self, uid, uname):
        self.cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
        self.cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (uname, uid))
        self.conn.commit()

    def update_info(self, key, text, photo=None):
        self.cursor.execute("UPDATE info SET text=?, photo=? WHERE key=?", (text, photo or "", key))
        self.conn.commit()

    def get_info(self, key):
        self.cursor.execute("SELECT text, photo FROM info WHERE key=?", (key,))
        return self.cursor.fetchone()

    def get_menu_photo(self):
        self.cursor.execute("SELECT value FROM settings WHERE key='menu_photo'")
        r = self.cursor.fetchone()
        return r[0] if r and r[0] else None

    def set_menu_photo(self, fid):
        self.cursor.execute("UPDATE settings SET value=? WHERE key='menu_photo'", (fid,))
        self.conn.commit()

    def save_trigger(self, kw, txt, photo=None, doc=None, vid=None, stk=None, voi=None, aud=None):
        self.cursor.execute("INSERT OR REPLACE INTO triggers (keyword, reply_text, reply_photo, reply_document, reply_video, reply_sticker, reply_voice, reply_audio) VALUES (?,?,?,?,?,?,?,?)",
            (kw, txt, photo, doc, vid, stk, voi, aud))
        self.conn.commit()

    def get_all_triggers(self):
        self.cursor.execute("SELECT keyword, reply_text, reply_photo, reply_document, reply_video, reply_sticker, reply_voice, reply_audio FROM triggers")
        return self.cursor.fetchall()

    def get_trigger_keywords(self):
        self.cursor.execute("SELECT keyword FROM triggers")
        return [r[0] for r in self.cursor.fetchall()]

    def delete_trigger(self, kw):
        self.cursor.execute("DELETE FROM triggers WHERE keyword=?", (kw,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def add_item(self, table, name, username, desc, photo):
        try:
            self.cursor.execute(f"INSERT INTO {table} (name, username, description, photo, views) VALUES (?,?,?,?,0)",
                                (name, username, desc, photo))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка add_item в {table}: {e}")
            return False

    def delete_item(self, table, name):
        self.cursor.execute(f"DELETE FROM {table} WHERE name=?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_items(self, table):
        self.cursor.execute(f"SELECT name, username, description, photo, views FROM {table}")
        return self.cursor.fetchall()

    def get_item_by_username(self, table, uname):
        self.cursor.execute(f"SELECT name, username, description, photo, views FROM {table} WHERE username=?", (uname,))
        item = self.cursor.fetchone()
        if item:
            self.cursor.execute(f"UPDATE {table} SET views=views+1 WHERE username=?", (uname,))
            self.conn.commit()
        return item

    def get_item_by_name(self, table, name):
        self.cursor.execute(f"SELECT name, username, description, photo, views FROM {table} WHERE name=?", (name,))
        item = self.cursor.fetchone()
        if item:
            self.cursor.execute(f"UPDATE {table} SET views=views+1 WHERE name=?", (name,))
            self.conn.commit()
        return item

    def get_popular_items(self, table, limit=5):
        self.cursor.execute(f"SELECT name, username, views FROM {table} WHERE views>0 ORDER BY views DESC LIMIT ?", (limit,))
        return self.cursor.fetchall()

    def increment_msg_count(self, uid):
        self.cursor.execute("UPDATE users SET msg_count=msg_count+1 WHERE user_id=?", (uid,))
        self.conn.commit()

    def get_global_top_users(self, limit, offset):
        ph = ','.join('?' * len(ADMIN_IDS))
        self.cursor.execute(f"SELECT username, msg_count, vip FROM users WHERE user_id NOT IN ({ph}) AND msg_count>0 ORDER BY msg_count DESC LIMIT ? OFFSET ?",
                            (*ADMIN_IDS, limit, offset))
        return self.cursor.fetchall()

    def get_global_total_users_count(self):
        ph = ','.join('?' * len(ADMIN_IDS))
        self.cursor.execute(f"SELECT COUNT(*) FROM users WHERE user_id NOT IN ({ph}) AND msg_count>0", (*ADMIN_IDS,))
        return self.cursor.fetchone()[0]

    def increment_daily_msg_count(self, uid, date):
        self.cursor.execute("INSERT INTO daily_stats (user_id, date, msg_count) VALUES (?,?,1) ON CONFLICT(user_id,date) DO UPDATE SET msg_count=msg_count+1", (uid, date))
        self.conn.commit()

    def get_daily_top_users(self, date, limit=3):
        ph = ','.join('?' * len(ADMIN_IDS))
        self.cursor.execute(f"""
            SELECT u.username, d.msg_count, u.vip FROM daily_stats d
            JOIN users u ON d.user_id=u.user_id
            WHERE d.date=? AND u.user_id NOT IN ({ph})
            ORDER BY d.msg_count DESC LIMIT ?
        """, (date, *ADMIN_IDS, limit))
        return self.cursor.fetchall()

    def clear_daily_stats(self, date):
        self.cursor.execute("DELETE FROM daily_stats WHERE date=?", (date,))
        self.conn.commit()

    def get_user_info(self, uid):
        self.cursor.execute("SELECT username, msg_count, first_seen, vip, wins, games_played, reputation FROM users WHERE user_id=?", (uid,))
        return self.cursor.fetchone()

    def get_user_id_by_username(self, uname):
        self.cursor.execute("SELECT user_id FROM users WHERE username=?", (uname,))
        r = self.cursor.fetchone()
        return r[0] if r else None

    def add_win(self, uid):
        self.cursor.execute("UPDATE users SET wins=wins+1, games_played=games_played+1 WHERE user_id=?", (uid,))
        self.conn.commit()
        self.cursor.execute("SELECT wins FROM users WHERE user_id=?", (uid,))
        r = self.cursor.fetchone()
        if r:
            if r[0] == 1: self.unlock_achievement(uid, "Первая кровь")
            if r[0] >= 5: self.unlock_achievement(uid, "Массовик")

    def add_game(self, uid):
        self.cursor.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (uid,))
        self.conn.commit()

    def is_vip(self, uid):
        self.cursor.execute("SELECT vip FROM users WHERE user_id=?", (uid,))
        r = self.cursor.fetchone()
        return r and r[0] == 1

    def set_vip(self, uid, vip):
        self.cursor.execute("UPDATE users SET vip=? WHERE user_id=?", (1 if vip else 0, uid))
        self.conn.commit()
        if vip: self.unlock_achievement(uid, "VIP")

    def add_donation(self, uid):
        self.cursor.execute("UPDATE users SET donations=donations+1 WHERE user_id=?", (uid,))
        self.conn.commit()
        self.cursor.execute("SELECT donations FROM users WHERE user_id=?", (uid,))
        r = self.cursor.fetchone()
        if r and r[0] >= 3: self.unlock_achievement(uid, "Топ донатер")

    def get_reputation(self, uid):
        self.cursor.execute("SELECT reputation FROM users WHERE user_id=?", (uid,))
        r = self.cursor.fetchone()
        return r[0] if r else 0

    def set_reputation(self, uid, lvl):
        if lvl not in (0,1,2): return False
        self.cursor.execute("UPDATE users SET reputation=? WHERE user_id=?", (lvl, uid))
        self.conn.commit()
        return True

    def is_banned(self, uid):
        self.cursor.execute("SELECT 1 FROM banned_users WHERE user_id=?", (uid,))
        return self.cursor.fetchone() is not None

    def ban_user(self, uid, reason=None):
        self.cursor.execute("INSERT OR IGNORE INTO banned_users (user_id, banned_at, reason) VALUES (?,?,?)", (uid, datetime.now().isoformat(), reason))
        self.conn.commit()

    def unban_user(self, uid):
        self.cursor.execute("DELETE FROM banned_users WHERE user_id=?", (uid,))
        self.conn.commit()

    def unlock_achievement(self, uid, ach):
        self.cursor.execute("SELECT 1 FROM user_achievements WHERE user_id=? AND ach_name=?", (uid, ach))
        if self.cursor.fetchone(): return False
        self.cursor.execute("INSERT INTO user_achievements (user_id, ach_name, earned_at) VALUES (?,?,?)", (uid, ach, datetime.now().isoformat()))
        self.conn.commit()
        return True

    def get_user_achievements(self, uid):
        self.cursor.execute("SELECT ach_name FROM user_achievements WHERE user_id=?", (uid,))
        return [r[0] for r in self.cursor.fetchall()]

    def get_stats(self, uid):
        self.cursor.execute("SELECT wins, games_played, vip, reputation FROM users WHERE user_id=?", (uid,))
        return self.cursor.fetchone() or (0,0,0,0)

    def close(self):
        self.conn.close()

db = Database()
atexit.register(db.close)

# =====================================================================
# АНТИФЛУД
# =====================================================================
class AntiFlood:
    def __init__(self):
        self.actions = defaultdict(list)
        self.warnings = defaultdict(lambda: {"warnings": 0, "banned_until": None})
        self.MAX_ACTIONS = 3; self.ACTION_WINDOW = 5
        self.REGISTER_COOLDOWN = 30; self.BINGO_COOLDOWN = 10
        self.WARNING_BAN_TIME = 60; self.HARD_BAN_TIME = 300

    def is_blocked(self, uid):
        if uid in ADMIN_IDS: return False
        w = self.warnings[uid]
        return bool(w["banned_until"] and datetime.now() < w["banned_until"])

    def get_ban_time(self, uid):
        w = self.warnings[uid]
        if w["banned_until"] and datetime.now() < w["banned_until"]:
            return int((w["banned_until"] - datetime.now()).total_seconds())
        return 0

    def check_action(self, uid, atype="default"):
        now = datetime.now()
        if uid in ADMIN_IDS: return True, None
        if self.is_blocked(uid): return False, f"🚫 Заблокированы. Осталось: {self.get_ban_time(uid)} сек"
        self.actions[uid] = [(ts, act) for ts, act in self.actions[uid] if (now - ts).total_seconds() < self.ACTION_WINDOW]
        if atype == "register":
            last = [ts for ts, act in self.actions[uid] if act == "register" and (now - ts).total_seconds() < self.REGISTER_COOLDOWN]
            if last: return False, f"⏳ Подождите {self.REGISTER_COOLDOWN - int((now-last[0]).total_seconds())} сек"
        if atype == "bingo":
            last = [ts for ts, act in self.actions[uid] if act == "bingo" and (now - ts).total_seconds() < self.BINGO_COOLDOWN]
            if last: return False, f"⏳ Подождите {self.BINGO_COOLDOWN - int((now-last[0]).total_seconds())} сек"
        if len(self.actions[uid]) >= self.MAX_ACTIONS:
            self.add_warning(uid)
            return False, f"⚠️ Флуд! Предупреждение {self.warnings[uid]['warnings']}/5"
        self.actions[uid].append((now, atype))
        return True, None

    def add_warning(self, uid):
        self.warnings[uid]["warnings"] += 1
        w = self.warnings[uid]["warnings"]
        if w >= 5: self.warnings[uid]["banned_until"] = datetime.now() + timedelta(seconds=self.HARD_BAN_TIME)
        elif w >= 3: self.warnings[uid]["banned_until"] = datetime.now() + timedelta(seconds=self.WARNING_BAN_TIME)

    def reset_warnings(self, uid):
        self.warnings[uid] = {"warnings": 0, "banned_until": None}

antiflood = AntiFlood()

# =====================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ БИНГО
# =====================================================================
players = {}
game_active = False
registration_open = False
registration_ever_opened = False
bingo_history = []
history_msg_id = None
progress_msg_id = None
players_table_msg_id = None
current_winner = None
game_paused = False
admin_form_data = {}
sponsor_links = []
last_activity = {}

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================
def get_rank(msg_count):
    for threshold, name, icon in reversed(RANKS):
        if msg_count >= threshold: return name, icon
    return "🌊 Залётный", "🌊"

def get_progress_bar(current, target, width=20):
    if target <= 0: return "█" * width
    progress = min(current / target, 1.0)
    return "█" * int(progress * width) + "░" * (width - int(progress * width))

def get_random_count():
    r = random.random() * 100
    if r < 65: return 1
    elif r < 85: return 2
    elif r < 93: return 3
    elif r < 98: return 4
    else: return 5

def extract_chat_id(url):
    if url.startswith("https://t.me/"): return "@" + url.split("/")[-1]
    elif url.startswith("@"): return url
    return url

def rep_text(level):
    return {0: "⚪ Обычный", 1: "🔶 Средний", 2: "🔴 Высокий"}.get(level, "⚪ Обычный")

async def safe_send(bot, chat_id, text, **kwargs):
    try: return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e: logger.error(f"Send error: {e}"); return None

async def safe_edit(bot, chat_id, msg_id, text, **kwargs):
    try: return await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, **kwargs)
    except Exception as e: logger.error(f"Edit error: {e}"); return None

async def safe_delete(bot, chat_id, msg_id):
    try: await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except: pass

async def safe_reply(message, text, **kwargs):
    try: return await message.reply_text(text, **kwargs)
    except Exception as e: logger.error(f"Reply error: {e}"); return None

async def delete_message_after(msg, delay=7):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

def format_quote_card(title, description, username, views, item_type="shop"):
    icons = {"shop": "🏪", "exch": "💱", "vpn": "🛡️", "job": "💼"}
    icon = icons.get(item_type, "📌")
    text = f"{icon} <b>{title}</b>\n\n📝 {description}\n"
    if username: text += f"\n👤 @{username}\n"
    text += f"\n👁️ {views} просмотров"
    return text

def profile_text(uid):
    info = db.get_user_info(uid)
    if not info: return "Нет данных."
    uname, cnt, first, vip, wins, games, rep = info
    rname, ricon = get_rank(cnt)
    next_th = None
    for th, nm, ic in RANKS:
        if cnt < th: next_th = th; next_nm = nm; next_ic = ic; break
    text = (
        f"👤 <b>Профиль @{uname}</b>\n━━━━━━━━━━━━━━\n"
        f"💬 Сообщений: {cnt}\n🏅 Ранг: {ricon} {rname}\n"
    )
    if next_th: text += f"📈 Прогресс: {get_progress_bar(cnt, next_th)}\n"
    else: text += "🏆 Максимальный ранг!\n"
    text += (
        f"━━━━━━━━━━━━━━\n🎰 Побед в бинго: {wins}\n🎲 Игр сыграно: {games}\n"
        f"🔰 Репутация: {rep_text(rep)}\n💎 Статус: {'👑 VIP' if vip else '⭐ Обычный'}\n"
        f"━━━━━━━━━━━━━━\n"
    )
    if first: text += f"🕐 В чате с: {first}\n"
    return text

# =====================================================================
# КЛАВИАТУРЫ
# =====================================================================
PINNED_MENU_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛍️ Открыть меню Brandoвичок", callback_data="open_menu")]
])

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎰 Бинго — игра на удачу", callback_data="mode_bingo")],
    [InlineKeyboardButton("🛍️ Магазины и обменники", callback_data="mode_shops")],
    [InlineKeyboardButton("📊 Статистика чата", callback_data="mode_stats")],
    [InlineKeyboardButton("ℹ️ Информация и правила", callback_data="mode_info")],
    [InlineKeyboardButton("🔗 Пригласить друга", callback_data="invite_friend")],
])

def bingo_menu():
    kb = []
    if registration_open:
        kb.append([InlineKeyboardButton("✍️ Записаться в игру", callback_data="bingo_register")])
        kb.append([InlineKeyboardButton("📋 Список участников", callback_data="bingo_players")])
    elif game_active:
        kb.append([InlineKeyboardButton("🔢 Мои числа", callback_data="bingo_my_combo")])
        kb.append([InlineKeyboardButton("📋 Участники", callback_data="bingo_players")])
        kb.append([InlineKeyboardButton("📊 Прогресс игры", callback_data="bingo_progress")])
    else:
        kb.append([InlineKeyboardButton("📜 Правила бинго", callback_data="info_rules_bingo")])
    kb.append([InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")])
    status = ""
    if registration_open: status = "🟢 <b>Регистрация открыта!</b>\n\n"
    elif game_active: status = "🔴 <b>Игра идёт</b>\n\n"
    else: status = "⚪ <b>Нет активной игры</b>\n\n"
    return InlineKeyboardMarkup(kb), status

SHOPS_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛍️ Магазины", callback_data="show_shops")],
    [InlineKeyboardButton("💱 Обменники", callback_data="show_exch")],
    [InlineKeyboardButton("💼 Вакансии", callback_data="show_jobs")],
    [InlineKeyboardButton("🔥 Популярное", callback_data="show_popular")],
    [InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")]
])

STATS_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Глобальный топ", callback_data="stat_global")],
    [InlineKeyboardButton("🏆 Топ за сегодня", callback_data="stat_today")],
    [InlineKeyboardButton("👤 Мой профиль", callback_data="stat_profile")],
    [InlineKeyboardButton("🏅 Мои достижения", callback_data="stat_achievements")],
    [InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")]
])

INFO_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📜 Правила чата", callback_data="info_rules_chat")],
    [InlineKeyboardButton("🎲 Правила бинго", callback_data="info_rules_bingo")],
    [InlineKeyboardButton("🔗 Полезные ссылки", callback_data="info_links")],
    [InlineKeyboardButton("🛡️ VPN", callback_data="show_vpn")],
    [InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")]
])

ADMIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛍️ Управление карточками", callback_data="admin_cards")],
    [InlineKeyboardButton("📝 Правила и ссылки", callback_data="admin_info")],
    [InlineKeyboardButton("👑 Пользователи", callback_data="admin_users")],
    [InlineKeyboardButton("🎲 Запустить бинго", callback_data="admin_start_bingo")],
    [InlineKeyboardButton("🖼️ Картинка меню", callback_data="admin_set_menu_photo")],
    [InlineKeyboardButton("📋 Список триггеров", callback_data="admin_list_triggers")],
])

ADMIN_CARDS_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("➕ Добавить", callback_data="admin_add_choose")],
    [InlineKeyboardButton("➖ Удалить", callback_data="admin_del_choose")],
    [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
])

def card_type_keyboard(action):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏪 Магазин", callback_data=f"admin_{action}_shop")],
        [InlineKeyboardButton("💱 Обменник", callback_data=f"admin_{action}_exch")],
        [InlineKeyboardButton("🛡️ VPN", callback_data=f"admin_{action}_vpn")],
        [InlineKeyboardButton("💼 Вакансия", callback_data=f"admin_{action}_job")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_cards")]
    ])

ADMIN_INFO_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📜 Правила чата", callback_data="admin_edit_rules_chat")],
    [InlineKeyboardButton("🎲 Правила бинго", callback_data="admin_edit_rules_bingo")],
    [InlineKeyboardButton("🔗 Полезные ссылки", callback_data="admin_edit_links")],
    [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
])

ADMIN_USERS_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("👑 Выдать VIP", callback_data="admin_give_vip")],
    [InlineKeyboardButton("🔰 Репутация", callback_data="admin_set_rep")],
    [InlineKeyboardButton("💰 Засчитать донат", callback_data="admin_add_donation")],
    [InlineKeyboardButton("🚫 Забанить", callback_data="admin_ban_user")],
    [InlineKeyboardButton("🔓 Разбанить", callback_data="admin_unban_user")],
    [InlineKeyboardButton("⚠️ Сбросить преды", callback_data="admin_reset_warn")],
    [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
])

WELCOME_TEXT = (
    "🤖 <b>Brandoвичок</b> приветствует тебя!\n\n"
    "🎰 <b>Бинго</b> — играй и выигрывай призы\n"
    "🛍️ <b>Магазины</b> — проверенные продавцы\n"
    "💱 <b>Обменники</b> — лучшие курсы\n"
    "💼 <b>Вакансии</b> — работа в твоём городе\n"
    "📊 <b>Статистика</b> — топ активных участников\n\n"
    "Выбери раздел:"
)

PRIVATE_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("👤 Мой профиль"), KeyboardButton("🏅 Достижения")],
    [KeyboardButton("📜 Правила чата"), KeyboardButton("🎲 Правила бинго")],
    [KeyboardButton("🔧 Админ-панель")]
], resize_keyboard=True)

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ МЕНЮ
# =====================================================================
def get_menu_owner_cb(context, msg_id):
    return context.bot_data.get(f"menu_{msg_id}")

def set_menu_owner_cb(context, msg_id, uid):
    context.bot_data[f"menu_{msg_id}"] = uid

def clear_menu_owner_cb(context, msg_id):
    if f"menu_{msg_id}" in context.bot_data:
        del context.bot_data[f"menu_{msg_id}"]

# =====================================================================
# ЕЖЕДНЕВНЫЙ СБРОС СТАТИСТИКИ
# =====================================================================
async def reset_daily_stats(context):
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    top = db.get_daily_top_users(yesterday, 3)
    medals = ["🥇", "🥈", "🥉"]
    if top:
        text = "🏆 <b>ТОП 3 АКТИВНЫХ ЗА ВЧЕРА!</b> 🏆\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, (uname, cnt, vip) in enumerate(top):
            vip_icon = "👑 " if vip else ""
            rname, ricon = get_rank(cnt)
            text += f"{medals[i]} {vip_icon}{ricon} @{(uname or '?')[:20]} — {cnt} сообщ. ({rname})\n"
        for cid in context.bot_data.get('group_chats', []):
            try: await context.bot.send_message(cid, text, parse_mode="HTML")
            except: pass
    db.clear_daily_stats(yesterday)

# =====================================================================
# КОМАНДЫ
# =====================================================================
async def start(update, context):
    uid = update.effective_user.id
    uname = update.effective_user.username or str(uid)
    db.ensure_user(uid, uname)
    if update.effective_chat.type == ChatType.PRIVATE:
        await safe_reply(update.message, f"👋 Привет, {uname}!\nЯ Brandoвичок — бот этого чата.\nИспользуй кнопки ниже.", reply_markup=PRIVATE_KEYBOARD)
    else:
        context.bot_data['game_chat_id'] = update.effective_chat.id
        if "group_chats" not in context.bot_data: context.bot_data["group_chats"] = set()
        context.bot_data["group_chats"].add(update.effective_chat.id)
        photo_id = db.get_menu_photo()
        if photo_id:
            await safe_send(context.bot, update.effective_chat.id, WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
        else:
            await update.message.reply_text(WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")

async def brand_command(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]: return
    photo_id = db.get_menu_photo()
    if photo_id:
        await update.message.reply_photo(photo_id, caption=WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
    else:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")

async def stat_command(update, context):
    uid = update.effective_user.id
    db.ensure_user(uid, update.effective_user.username or str(uid))
    page = context.user_data.get('stat_page', 0)
    users_per_page = 10
    total = db.get_global_total_users_count()
    offset = page * users_per_page
    users = db.get_global_top_users(users_per_page, offset)
    if not users: await safe_reply(update.message, "Пока нет данных."); return
    text = f"📊 <b>Топ активных</b> (стр. {page+1})\n\n"
    for i, (uname, cnt, vip) in enumerate(users, start=offset+1):
        vip_icon = "👑" if vip else ""; rname, ricon = get_rank(cnt)
        text += f"{i}. {vip_icon}{ricon} @{(uname or '?')[:20]} — {cnt} ({rname})\n"
    kb = []
    if page > 0: kb.append(InlineKeyboardButton("◀️", callback_data=f"stat_page_{page-1}"))
    if (page+1)*users_per_page < total: kb.append(InlineKeyboardButton("▶️", callback_data=f"stat_page_{page+1}"))
    markup = InlineKeyboardMarkup([kb]) if kb else None
    await safe_reply(update.message, text, reply_markup=markup, parse_mode="HTML")

async def topday_command(update, context):
    uid = update.effective_user.id
    db.ensure_user(uid, update.effective_user.username or str(uid))
    today = datetime.now().strftime("%Y-%m-%d"); top = db.get_daily_top_users(today, 3)
    medals = ["🥇","🥈","🥉"]
    if not top: await safe_reply(update.message, "Пока нет данных за сегодня."); return
    text = "🏆 <b>Топ за сегодня</b>\n\n"
    for i, (uname, cnt, vip) in enumerate(top):
        vip_icon = "👑" if vip else ""; rname, ricon = get_rank(cnt)
        text += f"{medals[i]} {vip_icon}{ricon} @{(uname or '?')[:20]} — {cnt} ({rname})\n"
    await safe_reply(update.message, text, parse_mode="HTML")

async def rank_command(update, context):
    uid = update.effective_user.id
    db.ensure_user(uid, update.effective_user.username or str(uid))
    row = db.cursor.execute("SELECT msg_count FROM users WHERE user_id=?", (uid,)).fetchone()
    cnt = row[0] if row else 0
    rname, ricon = get_rank(cnt)
    text = f"⭐ Ваш ранг: {ricon} <b>{rname}</b>\nСообщений: {cnt}\n"
    next_th = None
    for th, nm, ic in RANKS:
        if cnt < th: next_th = th; next_nm = nm; next_ic = ic; break
    if next_th:
        need = next_th - cnt
        text += f"До {next_ic} {next_nm}: {need} сообщ.\n{get_progress_bar(cnt, next_th)}"
    await safe_reply(update.message, text, parse_mode="HTML")

async def ktoeto_command(update, context):
    user = None
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
    elif context.args:
        uid = db.get_user_id_by_username(context.args[0].lstrip('@'))
        if uid:
            try: user = await context.bot.get_chat(uid)
            except: pass
    else: user = update.effective_user
    if not user: await safe_reply(update.message, "❌ Пользователь не найден."); return
    db.ensure_user(user.id, user.username or str(user.id))
    info = db.get_user_info(user.id)
    if not info: await safe_reply(update.message, "❌ Нет данных."); return
    await safe_reply(update.message, profile_text(user.id), parse_mode="HTML")

# =====================================================================
# ЗАКРЕПЛЕНИЕ МЕНЮ
# =====================================================================
async def bot_added_to_group(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]: return
    if not update.message or not update.message.new_chat_members: return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            context.bot_data['game_chat_id'] = update.effective_chat.id
            if "group_chats" not in context.bot_data: context.bot_data["group_chats"] = set()
            context.bot_data["group_chats"].add(update.effective_chat.id)
            photo_id = db.get_menu_photo()
            caption = "🤖 <b>Brandoвичок</b> готов к работе!\n\nНажми на кнопку чтобы открыть меню:"
            if photo_id:
                msg = await update.message.reply_photo(photo_id, caption=caption, reply_markup=PINNED_MENU_KEYBOARD, parse_mode="HTML")
            else:
                msg = await update.message.reply_text(caption, reply_markup=PINNED_MENU_KEYBOARD, parse_mode="HTML")
            try: await msg.pin(disable_notification=True)
            except: pass
            try: await update.message.delete()
            except: pass
            return

# =====================================================================
# ГЛАВНЫЙ КОЛБЭК-РОУТЕР
# =====================================================================
async def main_callback(update, context):
    query = update.callback_query; uid = query.from_user.id; mid = query.message.message_id; data = query.data

    if data == "open_menu":
        await query.answer()
        photo_id = db.get_menu_photo()
        if photo_id: await safe_send(context.bot, query.message.chat_id, WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
        else: await query.message.reply_text(WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
        return

    if data == "invite_friend":
        await invite_friend_handler(update, context); return

    owner = get_menu_owner_cb(context, mid)
    if owner and uid != owner:
        await query.answer("⚠️ Это меню другого пользователя. Нажмите «🛍️ Открыть меню» в закреплённом сообщении.", show_alert=True); return

    await query.answer()

    if data == "main_menu":
        clear_menu_owner_cb(context, mid)
        photo_id = db.get_menu_photo()
        if photo_id: msg = await safe_send(context.bot, query.message.chat_id, WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
        else: msg = await query.message.reply_text(WELCOME_TEXT, reply_markup=MAIN_MENU, parse_mode="HTML")
        if msg: set_menu_owner_cb(context, msg.message_id, uid)
        await safe_delete(context.bot, query.message.chat_id, mid); return
    if data == "mode_bingo":
        menu, status = bingo_menu(); await query.message.edit_text(f"{status}Выберите действие:", reply_markup=menu, parse_mode="HTML")
        set_menu_owner_cb(context, mid, uid); return
    if data == "mode_shops":
        await query.message.edit_text("🛍️ <b>Магазины и обменники</b>\nВыберите категорию:", reply_markup=SHOPS_MENU, parse_mode="HTML")
        set_menu_owner_cb(context, mid, uid); return
    if data == "mode_stats":
        await query.message.edit_text("📊 <b>Статистика чата</b>\nВыберите:", reply_markup=STATS_MENU, parse_mode="HTML")
        set_menu_owner_cb(context, mid, uid); return
    if data == "mode_info":
        await query.message.edit_text("ℹ️ <b>Информация</b>\nВыберите:", reply_markup=INFO_MENU, parse_mode="HTML")
        set_menu_owner_cb(context, mid, uid); return

    if data == "bingo_register": await bingo_register_handler(update, context); return
    if data == "bingo_my_combo": await bingo_my_combo_handler(update, context); return
    if data == "bingo_players": await bingo_players_handler(update, context); return
    if data == "bingo_progress": await bingo_progress_handler(update, context); return

    if data == "stat_global": await stat_global_callback(update, context); return
    if data == "stat_today": await stat_today_callback(update, context); return
    if data == "stat_profile":
        db.ensure_user(uid, query.from_user.username or str(uid))
        await query.message.edit_text(profile_text(uid), parse_mode="HTML"); return
    if data == "stat_achievements": await stat_achievements_callback(update, context); return
    if data.startswith("stat_page_"):
        page = int(data.split("_")[-1]); context.user_data['stat_page'] = page
        await stat_global_callback(update, context); return

    if data == "info_rules_chat":
        text, _ = db.get_info('rules_chat')
        await query.message.edit_text(f"📜 <b>ПРАВИЛА ЧАТА</b>\n\n{text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="mode_info")]]), parse_mode="HTML"); return
    if data == "info_rules_bingo":
        text, _ = db.get_info('rules_bingo')
        await query.message.edit_text(f"🎲 <b>ПРАВИЛА БИНГО</b>\n\n{text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="mode_bingo")]]), parse_mode="HTML"); return
    if data == "info_links":
        text, _ = db.get_info('links')
        await query.message.edit_text(f"🔗 <b>ПОЛЕЗНЫЕ ССЫЛКИ</b>\n\n{text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="mode_info")]]), parse_mode="HTML"); return
    if data == "show_vpn": await show_items_list(update, context, "vpn", "VPN", "mode_info", "vpn"); return

    if data == "show_shops": await show_items_list(update, context, "shops", "магазинов", "mode_shops", "shop"); return
    if data == "show_exch": await show_items_list(update, context, "exchangers", "обменников", "mode_shops", "exch"); return
    if data == "show_jobs": await show_items_list(update, context, "jobs", "вакансий", "mode_shops", "job"); return
    if data == "show_popular": await show_popular_handler(update, context); return

    if data.startswith("shop_"): await show_item_card(update, context, "shops", "Магазин", "show_shops", data[5:], "shop"); return
    if data.startswith("exch_"): await show_item_card(update, context, "exchangers", "Обменник", "show_exch", data[5:], "exch"); return
    if data.startswith("vpn_"): await show_item_card(update, context, "vpn", "VPN", "show_vpn", data[4:], "vpn"); return
    if data.startswith("job_"): await show_item_card(update, context, "jobs", "Вакансия", "show_jobs", data[4:], "job"); return

    if data.startswith("check_sponsor_"): await check_sponsor_subscription(update, context); return

    if data == "admin_menu": await query.message.edit_text("🔧 <b>АДМИН-ПАНЕЛЬ BRANDOВИЧКА</b>\nВыберите раздел:", reply_markup=ADMIN_MENU, parse_mode="HTML"); return
    if data == "admin_cards": await query.message.edit_text("🛍️ <b>Управление карточками</b>\nВыберите действие:", reply_markup=ADMIN_CARDS_MENU, parse_mode="HTML"); return
    if data == "admin_add_choose": await query.message.edit_text("➕ <b>Добавление</b>\nВыберите тип:", reply_markup=card_type_keyboard("add"), parse_mode="HTML"); return
    if data == "admin_del_choose": await query.message.edit_text("➖ <b>Удаление</b>\nВыберите тип:", reply_markup=card_type_keyboard("del"), parse_mode="HTML"); return
    if data == "admin_info": await query.message.edit_text("📝 <b>Редактирование информации</b>\nВыберите:", reply_markup=ADMIN_INFO_MENU, parse_mode="HTML"); return
    if data == "admin_users": await query.message.edit_text("👑 <b>Управление пользователями</b>\nВыберите действие:", reply_markup=ADMIN_USERS_MENU, parse_mode="HTML"); return

    if (data.startswith("admin_add_") or data.startswith("admin_del_") or data.startswith("admin_edit_") or
        data.startswith("admin_give_") or data.startswith("admin_set_") or data.startswith("admin_ban_") or
        data.startswith("admin_unban_") or data.startswith("admin_reset_") or data == "admin_set_menu_photo" or
        data == "admin_start_bingo" or data == "admin_list_triggers"):
        await admin_callback_handler(update, context); return

    if data.startswith("confirm_del_"): await confirm_delete_handler(update, context); return

# =====================================================================
# ПРИГЛАСИТЬ ДРУГА
# =====================================================================
async def invite_friend_handler(update, context):
    query = update.callback_query
    chat_id = context.bot_data.get('game_chat_id') or query.message.chat_id
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=chat_id,
            expire_date=datetime.now() + timedelta(hours=24),
            member_limit=1
        )
        text = (
            f"🔗 <b>Твоя персональная ссылка для друга:</b>\n\n"
            f"{invite_link.invite_link}\n\n"
            f"⚠️ <b>Ссылка одноразовая</b> — после первого перехода сгорит.\n"
            f"Отправь её другу, которому доверяешь!"
        )
        await query.answer("✅ Ссылка создана! Отправлена тебе в ЛС.", show_alert=True)
        try:
            await context.bot.send_message(query.from_user.id, text, parse_mode="HTML")
        except:
            await query.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await query.answer("❌ Не удалось создать ссылку. Бот должен быть администратором с правом приглашения.", show_alert=True)

# =====================================================================
# ПОКАЗ СПИСКОВ И КАРТОЧЕК
# =====================================================================
async def show_items_list(update, context, table, title, back_cb, item_type):
    query = update.callback_query
    items = db.get_items(table)
    if not items: await query.answer(f"📭 {title} пока пуст.", show_alert=True); return
    kb = []
    for name, username, desc, photo, views in items:
        lbl = f"🖼️ {name}" if photo else name
        kb.append([InlineKeyboardButton(lbl, callback_data=f"{item_type}_{username if username else name}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data=back_cb)])
    await query.message.edit_text(f"📋 {title}:", reply_markup=InlineKeyboardMarkup(kb))
    set_menu_owner_cb(context, query.message.message_id, query.from_user.id)

async def show_item_card(update, context, table, title, back_cb, identifier, item_type):
    query = update.callback_query
    item = db.get_item_by_name(table, identifier) if table == "jobs" else db.get_item_by_username(table, identifier)
    if not item: await query.answer("❌ Не найден.", show_alert=True); return
    name, username, description, photo_id, views = item
    caption = format_quote_card(name, description, username, views, item_type)
    kb = []
    if username: kb.append([InlineKeyboardButton("📩 Написать", url=f"https://t.me/{username}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data=back_cb)])
    if photo_id:
        await query.message.delete()
        msg = await context.bot.send_photo(query.message.chat_id, photo_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        msg = await query.message.edit_text(caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    set_menu_owner_cb(context, msg.message_id, query.from_user.id)

async def show_popular_handler(update, context):
    query = update.callback_query
    pop_shops = db.get_popular_items("shops", 3); pop_exch = db.get_popular_items("exchangers", 3)
    text = "🔥 <b>Популярное</b>\n\n"
    if pop_shops: 
        text += "🛍️ <b>Магазины:</b>\n"
        for n, u, v in pop_shops: text += f"• {n} (@{u}) — {v}👁️\n"
    if pop_exch:
        text += "💱 <b>Обменники:</b>\n"
        for n, u, v in pop_exch: text += f"• {n} (@{u}) — {v}👁️\n"
    if not pop_shops and not pop_exch: text += "Пока ничего нет."
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="mode_shops")]]), parse_mode="HTML")

# =====================================================================
# БИНГО КОЛБЭКИ
# =====================================================================
async def bingo_register_handler(update, context):
    query = update.callback_query; uid = query.from_user.id; uname = query.from_user.username or str(uid)
    if uid in players: await query.answer("⚠️ Вы уже в игре!", show_alert=True); return
    if not registration_open: await query.answer("🔒 Регистрация сейчас закрыта.", show_alert=True); return
    if db.is_banned(uid): await query.answer("🚫 Вы заблокированы!", show_alert=True); return
    can, err = antiflood.check_action(uid, "register")
    if not can: await query.answer(err, show_alert=True); return
    if sponcor_links:
        not_sub = []
        for s in sponcor_links:
            try:
                m = await context.bot.get_chat_member(s['chat_id'], uid)
                if m.status in ['left', 'kicked']: not_sub.append(s)
            except: pass
        if not_sub:
            kb = [[InlineKeyboardButton(s['text'], url=s['url'])] for s in not_sub]
            kb.append([InlineKeyboardButton("✅ Проверить подписки", callback_data=f"check_sponsor_{uid}")])
            await query.message.edit_text("⚠️ Для участия подпишитесь на спонсоров:", reply_markup=InlineKeyboardMarkup(kb)); return
    if db.is_vip(uid):
        text = f"@{uname}\n👑 <b>VIP!</b>\n📝 Теперь отправь в чат <b>5 чисел</b> от 1 до 100 через пробел.\nПример: 7 15 32 68 91"
        context.user_data['awaiting_numbers'] = 'vip'
    else:
        text = f"@{uname}\n🎯 Теперь отправь в чат <b>6 чисел</b> от 1 до 100 через пробел.\nПример: 7 15 32 68 91 42"
        context.user_data['awaiting_numbers'] = 'normal'
    await safe_send(query.message.chat.bot, query.message.chat_id, text, parse_mode="HTML")

async def check_sponsor_subscription(update, context):
    query = update.callback_query; uid = query.from_user.id
    not_sub = []
    for s in sponcor_links:
        try:
            m = await context.bot.get_chat_member(s['chat_id'], uid)
            if m.status in ['left', 'kicked']: not_sub.append(s)
        except: pass
    if not_sub:
        kb = [[InlineKeyboardButton(s['text'], url=s['url'])] for s in not_sub]
        kb.append([InlineKeyboardButton("✅ Проверить подписки", callback_data=f"check_sponsor_{uid}")])
        await query.message.edit_text(f"⚠️ Подпишитесь на всех! Осталось: {len(not_sub)}", reply_markup=InlineKeyboardMarkup(kb)); return
    await query.message.delete()
    uname = query.from_user.username or str(uid)
    if db.is_vip(uid):
        text = f"@{uname}\n👑 <b>VIP!</b>\n📝 Теперь отправь в чат <b>5 чисел</b> от 1 до 100 через пробел.\nПример: 7 15 32 68 91"
        context.user_data['awaiting_numbers'] = 'vip'
    else:
        text = f"@{uname}\n🎯 Теперь отправь в чат <b>6 чисел</b> от 1 до 100 через пробел.\nПример: 7 15 32 68 91 42"
        context.user_data['awaiting_numbers'] = 'normal'
    await safe_send(query.message.chat.bot, query.message.chat_id, text, parse_mode="HTML")

async def bingo_my_combo_handler(update, context):
    query = update.callback_query; uid = query.from_user.id
    if uid in players:
        p = players[uid]
        await query.message.edit_text(f"🔢 Твои числа: {', '.join(map(str, p['numbers']))}\n✅ Выпало: {', '.join(map(str, p['found'])) or 'нет'}\n🎯 Осталось: {p['max_needed'] - len(p['found'])}")
    else: await query.answer("❌ Ты не в игре.", show_alert=True)

async def bingo_players_handler(update, context):
    query = update.callback_query
    if not players: await query.answer("📭 Нет участников.", show_alert=True); return
    msg = "📋 <b>Участники:</b>\n\n"
    for uid, p in players.items():
        wins, _, vip, rep = db.get_stats(uid)
        msg += f"👤 @{p['username']} {'👑' if vip else ''} ({rep_text(rep)}): {len(p['found'])}/{p['max_needed']} | побед: {wins}\n"
    await query.message.edit_text(msg, parse_mode="HTML")

async def bingo_progress_handler(update, context):
    query = update.callback_query
    if not players: await query.answer("📭 Нет участников.", show_alert=True); return
    lines = []
    for uid, p in players.items():
        rep = db.get_reputation(uid); vip = "👑" if db.is_vip(uid) else ""
        lines.append(f"{vip}@{p['username']} ({rep_text(rep)}): {len(p['found'])}/{p['max_needed']}")
    await query.message.edit_text("📊 <b>Прогресс игры:</b>\n" + "\n".join(lines), parse_mode="HTML")

# =====================================================================
# ОБРАБОТКА ЧИСЕЛ ДЛЯ БИНГО
# =====================================================================
async def handle_bingo_numbers(update, context):
    if 'awaiting_numbers' not in context.user_data:
        text = update.message.text.strip(); parts = text.split()
        if len(parts) in (5, 6) and all(p.lstrip('-').isdigit() for p in parts):
            if registration_open:
                msg = await safe_reply(update.message, f"@{update.effective_user.username}, чтобы записаться — нажми ✍️ Записаться в меню Бинго 🎰")
                asyncio.create_task(delete_message_after(msg, 7))
        return
    uid = update.effective_user.id; uname = update.effective_user.username or str(uid)
    mode = context.user_data.pop('awaiting_numbers')
    text = update.message.text.strip(); parts = text.split()
    needed = 5 if mode == 'vip' else 6
    if len(parts) != needed:
        msg = await safe_reply(update.message, f"❌ @{uname}, нужно ровно {needed} чисел!"); asyncio.create_task(delete_message_after(msg, 7))
        context.user_data['awaiting_numbers'] = mode; return
    try:
        nums = [int(x) for x in parts]
        if len(set(nums)) != needed or min(nums) < 1 or max(nums) > 100: raise ValueError
    except:
        msg = await safe_reply(update.message, f"❌ @{uname}, числа от 1 до 100, разные!"); asyncio.create_task(delete_message_after(msg, 7))
        context.user_data['awaiting_numbers'] = mode; return
    players[uid] = {"numbers": nums, "found": set(), "username": uname, "max_needed": needed}
    last_activity[uid] = datetime.now()
    msg = await safe_reply(update.message, f"✅ @{uname}, ты в игре!\nТвои числа: {', '.join(map(str, nums))}")
    asyncio.create_task(delete_message_after(msg, 10))
    chat_id = context.bot_data.get('game_chat_id')
    if chat_id: await update_players_table(context, chat_id)

async def update_players_table(context, chat_id):
    global players_table_msg_id
    if not players:
        if players_table_msg_id: await safe_delete(context.bot, chat_id, players_table_msg_id); players_table_msg_id = None
        return
    lines = []
    for i, (uid, data) in enumerate(players.items(), 1):
        vip_icon = "👑" if db.is_vip(uid) else ""; rep = db.get_reputation(uid)
        nums = " | ".join(map(str, data["numbers"]))
        lines.append(f"{i}. {vip_icon}{rep_text(rep)} @{data['username']}\n   🎯 {nums}")
    text = "📋 <b>ТАБЛИЦА УЧАСТНИКОВ</b>\n\n" + "\n".join(lines)
    if players_table_msg_id: await safe_edit(context.bot, chat_id, players_table_msg_id, text, parse_mode="HTML")
    else:
        msg = await safe_send(context.bot, chat_id, text, parse_mode="HTML")
        if msg: players_table_msg_id = msg.message_id

# =====================================================================
# БИНГО АДМИН КОМАНДЫ
# =====================================================================
async def startreg_command(update, context):
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    chat_id = context.bot_data.get('game_chat_id')
    chat_info = ""
    if chat_id:
        try:
            chat = await context.bot.get_chat(chat_id)
            chat_info = f"\n📢 Группа: <b>{chat.title}</b>"
        except: chat_info = f"\n📢 ID чата: {chat_id}"
    else: chat_info = "\n⚠️ Группа не выбрана! Отправьте /start в группе."
    context.user_data['setting_up_bingo'] = True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Без спонсоров", callback_data="setup_no_sponsor")],
        [InlineKeyboardButton("🔗 Добавить спонсора", callback_data="setup_add_sponsor")],
    ])
    if hasattr(update, 'message') and update.message:
        await safe_reply(update.message, f"🎲 <b>Настройка игры в бинго</b>{chat_info}\n\nНужны спонсоры для участия?", reply_markup=kb, parse_mode="HTML")
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(f"🎲 <b>Настройка игры в бинго</b>{chat_info}\n\nНужны спонсоры для участия?", reply_markup=kb, parse_mode="HTML")

async def setup_callback(update, context):
    query = update.callback_query
    if not db.is_admin(query.from_user.id): await query.answer("❌ Только админ.", show_alert=True); return
    await query.answer()
    global registration_open, sponcor_links, registration_ever_opened
    if query.data == "setup_no_sponsor":
        sponcor_links = []; registration_open = True; registration_ever_opened = True
        await query.message.edit_text("✅ Регистрация открыта! Без спонсоров.\n\nВ группе появится уведомление."); await notify_group_registration(context)
    elif query.data == "setup_add_sponsor":
        sponcor_links = []; context.user_data['admin_step'] = 'wait_sponsor_name'
        await query.message.edit_text("🔗 <b>Шаг 1/2</b>\nВведите название кнопки спонсора:", parse_mode="HTML")

async def notify_group_registration(context):
    chat_id = context.bot_data.get('game_chat_id')
    if not chat_id: logger.error("❌ game_chat_id не задан!"); return
    notification = (
        "🎲 <b>РЕГИСТРАЦИЯ НА БИНГО ОТКРЫТА!</b>\n\n"
        "📝 <b>Как записаться:</b>\n"
        "1️⃣ Нажми на кнопку «🎰 Бинго» в меню\n"
        "2️⃣ Нажми «✍️ Записаться в игру»\n"
        "3️⃣ Отправь свои числа в чат\n\n"
        "👑 VIP: 5 чисел | 💎 Обычные: 6 чисел\n"
        "🔢 Числа от 1 до 100, все разные\n\n"
        "Успей записаться! 🎯"
    )
    menu, _ = bingo_menu()
    await safe_send(context.bot, chat_id, notification, reply_markup=menu, parse_mode="HTML")

async def stopreg_command(update, context):
    global game_active, registration_open
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    if not registration_ever_opened: await safe_reply(update.message, "❌ Регистрация ещё не открывалась. Используйте /startreg в ЛС."); return
    if registration_open:
        if not players: await safe_reply(update.message, "❌ Нет участников. Дождитесь, пока кто-нибудь запишется."); return
        registration_open = False; game_active = True
        menu, _ = bingo_menu()
        await safe_reply(update.message, f"🚫 Регистрация закрыта!\n🎲 <b>Игра началась!</b>\nУчастников: {len(players)}\n\nКрутите числа: /bingo", reply_markup=menu, parse_mode="HTML")
    else: await safe_reply(update.message, "❌ Регистрация уже закрыта. Используйте /openreg чтобы переоткрыть.")

async def openreg_command(update, context):
    global registration_open, game_active
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    if game_active: await safe_reply(update.message, "❌ Игра уже идёт. Нельзя открыть регистрацию во время игры."); return
    if registration_open: await safe_reply(update.message, "❌ Регистрация и так открыта."); return
    if not registration_ever_opened: await safe_reply(update.message, "❌ Сначала откройте регистрацию через /startreg в ЛС."); return
    registration_open = True; game_active = False
    menu, _ = bingo_menu()
    await safe_reply(update.message, "🟢 <b>Регистрация снова открыта!</b>\nУспейте записаться! ✍️", reply_markup=menu, parse_mode="HTML")

async def bingo_command(update, context):
    global players, bingo_history, history_msg_id, progress_msg_id
    global registration_open, current_winner, game_paused, sponcor_links
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    can, err = antiflood.check_action(update.effective_user.id, "bingo")
    if not can: await safe_reply(update.message, err); return
    if not game_active: await safe_reply(update.message, "❌ Игра не активна. Сначала закройте регистрацию: /stopreg"); return
    if game_paused: await safe_reply(update.message, "⏸ Игра на паузе. Подтвердите победителя в ЛС."); return
    if not players: await safe_reply(update.message, "Нет участников."); return
    if registration_open: registration_open = False
    count = get_random_count()
    numbers = [random.randint(1, 100) for _ in range(count)]
    numbers_str = ", ".join(str(n) for n in numbers)
    await safe_reply(update.message, f"🎲 Выпало: {numbers_str}")
    bingo_history.append(f"🎲 {numbers_str}")
    for num in numbers:
        for uid, data in players.items():
            if num in data["numbers"] and num not in data["found"]:
                data["found"].add(num)
    winners = [(uid, data["username"]) for uid, data in players.items() if len(data["found"]) == data["max_needed"]]
    if winners:
        winner_uid, winner_uname = random.choice(winners)
        current_winner = {"user_id": winner_uid, "username": winner_uname}; game_paused = True
        await safe_reply(update.message, f"🏆 <b>Победитель: @{winner_uname}!</b>\nАдмин назначает приз в ЛС.\nОстальные — не расстраивайтесь, повезёт в следующий раз!", parse_mode="HTML")
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(aid, f"🎁 <b>Назначьте приз для @{winner_uname}!</b>\n\nНапишите название приза:", parse_mode="HTML")
                admin_form_data[aid] = {"winner_id": winner_uid, "winner_username": winner_uname, "prize": "", "congrats": "", "chat_id": update.effective_chat.id}
            except: pass
    else: await update_progress_table(update, context)
    history = bingo_history[-30:]
    text = "🎰 История:\n" + "\n".join(history)
    if history_msg_id: await safe_edit(context.bot, update.effective_chat.id, history_msg_id, text)
    else:
        msg = await safe_send(context.bot, update.effective_chat.id, text)
        if msg: history_msg_id = msg.message_id

async def stopgame_command(update, context):
    global game_active, players, bingo_history, history_msg_id, progress_msg_id
    global registration_open, current_winner, game_paused, players_table_msg_id, sponcor_links, registration_ever_opened
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    game_active = False; players.clear(); bingo_history.clear(); history_msg_id = None
    progress_msg_id = None; registration_open = False; current_winner = None
    game_paused = False; players_table_msg_id = None; sponcor_links = []; registration_ever_opened = False
    await safe_reply(update.message, "⏹ Игра полностью остановлена. Данные очищены.")

async def update_progress_table(update, context):
    global progress_msg_id
    if not game_active or not players: return
    lines = []
    for uid, data in players.items():
        rep = db.get_reputation(uid); vip = "👑" if db.is_vip(uid) else ""
        lines.append(f"{vip}@{data['username']} ({rep_text(rep)}): {len(data['found'])}/{data['max_needed']}")
    text = "📊 Прогресс:\n" + "\n".join(lines)
    chat_id = update.effective_chat.id
    if progress_msg_id: await safe_edit(context.bot, chat_id, progress_msg_id, text)
    else:
        msg = await safe_send(context.bot, chat_id, text)
        if msg: progress_msg_id = msg.message_id

# =====================================================================
# СТАТИСТИКА КОЛБЭКИ
# =====================================================================
async def stat_global_callback(update, context):
    query = update.callback_query
    db.ensure_user(query.from_user.id, query.from_user.username or str(query.from_user.id))
    page = context.user_data.get('stat_page', 0); users_per_page = 10
    total = db.get_global_total_users_count(); offset = page * users_per_page
    users = db.get_global_top_users(users_per_page, offset)
    if not users: await query.answer("📭 Пока нет данных.", show_alert=True); return
    text = f"📊 <b>Топ активных</b> (стр. {page+1})\n\n"
    for i, (uname, cnt, vip) in enumerate(users, start=offset+1):
        vip_icon = "👑" if vip else ""; rname, ricon = get_rank(cnt)
        text += f"{i}. {vip_icon}{ricon} @{(uname or '?')[:20]} — {cnt} ({rname})\n"
    kb = []
    if page > 0: kb.append(InlineKeyboardButton("◀️", callback_data=f"stat_page_{page-1}"))
    if (page+1)*users_per_page < total: kb.append(InlineKeyboardButton("▶️", callback_data=f"stat_page_{page+1}"))
    markup = InlineKeyboardMarkup([kb]) if kb else None
    await query.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

async def stat_today_callback(update, context):
    query = update.callback_query
    db.ensure_user(query.from_user.id, query.from_user.username or str(query.from_user.id))
    today = datetime.now().strftime("%Y-%m-%d"); top = db.get_daily_top_users(today, 3)
    medals = ["🥇","🥈","🥉"]
    if not top: await query.answer("📭 Пока нет данных за сегодня.", show_alert=True); return
    text = "🏆 <b>Топ за сегодня</b>\n\n"
    for i, (uname, cnt, vip) in enumerate(top):
        vip_icon = "👑" if vip else ""; rname, ricon = get_rank(cnt)
        text += f"{medals[i]} {vip_icon}{ricon} @{(uname or '?')[:20]} — {cnt} ({rname})\n"
    await query.message.edit_text(text, parse_mode="HTML")

async def stat_achievements_callback(update, context):
    query = update.callback_query; uid = query.from_user.id
    earned = db.get_user_achievements(uid)
    all_ach = db.cursor.execute("SELECT name, description, icon FROM achievements ORDER BY id").fetchall()
    text = "🏅 <b>Мои достижения:</b>\n\n"
    for name, desc, icon in all_ach:
        text += f"{icon} {name} – {desc} {'✅' if name in earned else '❌'}\n"
    await query.message.edit_text(text, parse_mode="HTML")

# =====================================================================
# АДМИН-ПАНЕЛЬ
# =====================================================================
async def admin_panel(update, context):
    if not db.is_admin(update.effective_user.id): await safe_reply(update.message, "❌ Только админ."); return
    context.user_data.clear()
    await safe_reply(update.message, "🔧 <b>АДМИН-ПАНЕЛЬ BRANDOВИЧКА</b>\nВыберите раздел:", reply_markup=ADMIN_MENU, parse_mode="HTML")

async def admin_callback_handler(update, context):
    query = update.callback_query
    if not db.is_admin(query.from_user.id): await query.answer("❌ Только админ.", show_alert=True); return
    await query.answer(); action = query.data
    if action == "admin_set_menu_photo":
        context.user_data['admin_step'] = 'wait_menu_photo'; await query.message.edit_text("🖼️ Отправьте новую картинку для главного меню:"); return
    if action == "admin_start_bingo":
        await startreg_command(query, context); return
    if action == "admin_list_triggers":
        kws = db.get_trigger_keywords()
        if not kws: await query.message.edit_text("📭 Триггеров нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]]))
        else: await query.message.edit_text("📋 <b>Триггеры:</b>\n" + "\n".join(f"• {k}" for k in kws), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]]), parse_mode="HTML")
        return
    if "edit_rules_chat" in action:
        context.user_data['admin_step'] = 'wait_info'; context.user_data['admin_info_key'] = 'rules_chat'
        await query.message.edit_text("📝 Отправьте новый текст правил чата:"); return
    if "edit_rules_bingo" in action:
        context.user_data['admin_step'] = 'wait_info'; context.user_data['admin_info_key'] = 'rules_bingo'
        await query.message.edit_text("📝 Отправьте новый текст правил бинго:"); return
    if "edit_links" in action:
        context.user_data['admin_step'] = 'wait_info'; context.user_data['admin_info_key'] = 'links'
        await query.message.edit_text("📝 Отправьте новый текст ссылок:"); return
    if action.startswith("admin_add_") and action not in ("admin_add_choose", "admin_add_donation"):
        table = action.replace("admin_add_", ""); table = TABLE_MAP.get(table, table)
        context.user_data['admin_step'] = 'wait_name'; context.user_data['admin_table'] = table
        names = {"shops": "магазина", "exchangers": "обменника", "vpn": "VPN", "jobs": "вакансии"}
        await query.message.edit_text(f"🏪 <b>Добавление {names.get(table, '')}</b>\nШаг 1/4: Введите название:", parse_mode="HTML"); return
    if action.startswith("admin_del_") and action not in ("admin_del_choose",):
        table = action.replace("admin_del_", ""); table = TABLE_MAP.get(table, table)
        context.user_data['admin_step'] = 'wait_delete'; context.user_data['admin_table'] = table
        await query.message.edit_text(f"🗑 Введите точное название для удаления:"); return
    if action == "admin_give_vip": context.user_data['admin_step'] = 'wait_vip_user'; await query.message.edit_text("👑 Введите username для выдачи VIP:"); return
    if action == "admin_set_rep": context.user_data['admin_step'] = 'wait_rep'; await query.message.edit_text("🔰 Введите: username уровень (0/1/2)\nПример: @user 1"); return
    if action == "admin_add_donation": context.user_data['admin_step'] = 'wait_donation'; await query.message.edit_text("💰 Введите username для засчитывания доната:"); return
    if action == "admin_ban_user": context.user_data['admin_step'] = 'wait_ban'; await query.message.edit_text("🚫 Введите ID пользователя для бана:"); return
    if action == "admin_unban_user": context.user_data['admin_step'] = 'wait_unban'; await query.message.edit_text("🔓 Введите ID пользователя для разбана:"); return
    if action == "admin_reset_warn": context.user_data['admin_step'] = 'wait_reset_warn'; await query.message.edit_text("⚠️ Введите username для сброса предупреждений:"); return

async def admin_input_handler(update, context):
    global game_active, players, bingo_history, history_msg_id, progress_msg_id
    global game_paused, players_table_msg_id, current_winner, sponcor_links, registration_open
    if not db.is_admin(update.effective_user.id): return
    if not update.message: return
    text = update.message.text or update.message.caption or ""
    photo = update.message.photo[-1].file_id if update.message.photo else None

    if update.effective_user.id in admin_form_data:
        data = admin_form_data[update.effective_user.id]
        if not data['prize']:
            data['prize'] = text if text else "Приз"
            await safe_reply(update.message, "🎁 Приз сохранён. Теперь напишите поздравление (или '-' если без):"); return
        else:
            data['congrats'] = text if text else ""
            winner_uid = data['winner_id']; winner_uname = data['winner_username']
            prize = data['prize']; congrats = data['congrats'] if data['congrats'] != '-' else ""; chat_id = data['chat_id']
            publish_text = f"🏆 <b>ПОБЕДИТЕЛЬ ОПРЕДЕЛЁН!</b>\n\n👤 @{winner_uname}\n🎁 Приз: {prize}\n"
            if congrats: publish_text += f"💬 {congrats}\n"
            await safe_send(context.bot, chat_id, publish_text, parse_mode="HTML")
            db.add_win(winner_uid)
            for uid in players:
                if uid != winner_uid: db.add_game(uid)
            del admin_form_data[update.effective_user.id]
            game_active = False; players.clear(); bingo_history.clear()
            history_msg_id = None; progress_msg_id = None; game_paused = False
            players_table_msg_id = None; current_winner = None; sponcor_links = []
            global registration_ever_opened; registration_ever_opened = False
            await safe_reply(update.message, "✅ Победитель опубликован, игра завершена!"); return

    if context.user_data.get('setting_up_bingo'):
        step = context.user_data.get('admin_step', '')
        if step == 'wait_sponsor_name':
            context.user_data['sponsor_name'] = text; context.user_data['admin_step'] = 'wait_sponsor_url'
            await safe_reply(update.message, "🔗 Введите ссылку на спонсора (https://t.me/... или @username):"); return
        elif step == 'wait_sponsor_url':
            name = context.user_data.get('sponsor_name', 'Спонсор'); url = text.strip(); chat_id = extract_chat_id(url)
            sponcor_links.append({"text": name, "url": url, "chat_id": chat_id})
            context.user_data.pop('admin_step', None); context.user_data.pop('setting_up_bingo', None)
            registration_open = True
            global registration_ever_opened; registration_ever_opened = True
            await safe_reply(update.message, f"✅ Спонсор «{name}» добавлен! Регистрация открыта.")
            await notify_group_registration(context); return

    if text == "👤 Мой профиль":
        db.ensure_user(update.effective_user.id, update.effective_user.username or str(update.effective_user.id))
        await safe_reply(update.message, profile_text(update.effective_user.id), parse_mode="HTML"); return
    if text == "🏅 Достижения":
        await stat_achievements_callback_private(update, context); return
    if text == "📜 Правила чата":
        t, _ = db.get_info('rules_chat'); await safe_reply(update.message, f"📜 <b>ПРАВИЛА ЧАТА</b>\n\n{t}", parse_mode="HTML"); return
    if text == "🎲 Правила бинго":
        t, _ = db.get_info('rules_bingo'); await safe_reply(update.message, f"🎲 <b>ПРАВИЛА БИНГО</b>\n\n{t}", parse_mode="HTML"); return
    if text == "🔧 Админ-панель": await admin_panel(update, context); return

    step = context.user_data.get('admin_step', '')
    if not step: return

    if step == 'wait_name':
        context.user_data['temp_name'] = text; context.user_data['admin_step'] = 'wait_username'
        await safe_reply(update.message, "👤 Введите username (без @):")
    elif step == 'wait_username':
        context.user_data['temp_username'] = text; context.user_data['admin_step'] = 'wait_desc'
        await safe_reply(update.message, "📝 Введите описание:")
    elif step == 'wait_desc':
        context.user_data['temp_desc'] = text; context.user_data['admin_step'] = 'wait_photo'
        await safe_reply(update.message, "🖼️ Отправьте фото или /skip:")
    elif step == 'wait_photo':
        if text and text.lower() == "/skip": photo = None
        elif not photo: await safe_reply(update.message, "❌ Отправьте фото или напишите /skip чтобы пропустить."); return
        table = context.user_data.get('admin_table', '')
        ok = db.add_item(table, context.user_data['temp_name'], context.user_data['temp_username'], context.user_data['temp_desc'], photo)
        await safe_reply(update.message, "✅ Добавлено!" if ok else "❌ Ошибка (возможно, дубль).")
        context.user_data['admin_step'] = None
    elif step == 'wait_info':
        key = context.user_data.get('admin_info_key', ''); db.update_info(key, text or "", photo)
        await safe_reply(update.message, "✅ Обновлено!"); context.user_data['admin_step'] = None
    elif step == 'wait_menu_photo':
        if update.message.photo: db.set_menu_photo(photo); await safe_reply(update.message, "✅ Картинка меню обновлена!")
        else: await safe_reply(update.message, "❌ Отправьте фото.")
        context.user_data['admin_step'] = None
    elif step == 'wait_delete':
        table = context.user_data.get('admin_table', '')
        if db.delete_item(table, text): await safe_reply(update.message, "✅ Удалено!")
        else: await safe_reply(update.message, "❌ Не найдено.")
        context.user_data['admin_step'] = None
    elif step == 'wait_vip_user':
        uid = db.get_user_id_by_username(text.lstrip('@'))
        if uid: db.set_vip(uid, True); await safe_reply(update.message, f"✅ @{text.lstrip('@')} получил VIP!")
        else: await safe_reply(update.message, "❌ Пользователь не найден.")
        context.user_data['admin_step'] = None
    elif step == 'wait_rep':
        parts = text.split()
        if len(parts) >= 2:
            uid = db.get_user_id_by_username(parts[0].lstrip('@'))
            if uid:
                try:
                    lvl = int(parts[1])
                    if db.set_reputation(uid, lvl): await safe_reply(update.message, f"✅ Репутация обновлена! ({rep_text(lvl)})")
                    else: await safe_reply(update.message, "❌ Уровень 0, 1 или 2.")
                except: await safe_reply(update.message, "❌ Уровень — число.")
            else: await safe_reply(update.message, "❌ Пользователь не найден.")
        context.user_data['admin_step'] = None
    elif step == 'wait_donation':
        uid = db.get_user_id_by_username(text.lstrip('@'))
        if uid: db.add_donation(uid); await safe_reply(update.message, "✅ Донат засчитан!")
        else: await safe_reply(update.message, "❌ Пользователь не найден.")
        context.user_data['admin_step'] = None
    elif step == 'wait_ban':
        try: uid = int(text); db.ban_user(uid); await safe_reply(update.message, f"✅ {uid} забанен.")
        except: await safe_reply(update.message, "❌ ID — число.")
        context.user_data['admin_step'] = None
    elif step == 'wait_unban':
        try: uid = int(text); db.unban_user(uid); await safe_reply(update.message, f"✅ {uid} разбанен.")
        except: await safe_reply(update.message, "❌ ID — число.")
        context.user_data['admin_step'] = None
    elif step == 'wait_reset_warn':
        uid = db.get_user_id_by_username(text.lstrip('@'))
        if uid: antiflood.reset_warnings(uid); await safe_reply(update.message, f"✅ Предупреждения @{text.lstrip('@')} сброшены.")
        else: await safe_reply(update.message, "❌ Пользователь не найден.")
        context.user_data['admin_step'] = None

async def stat_achievements_callback_private(update, context):
    uid = update.effective_user.id
    earned = db.get_user_achievements(uid)
    all_ach = db.cursor.execute("SELECT name, description, icon FROM achievements ORDER BY id").fetchall()
    text = "🏅 <b>Мои достижения:</b>\n\n"
    for name, desc, icon in all_ach:
        text += f"{icon} {name} – {desc} {'✅' if name in earned else '❌'}\n"
    await safe_reply(update.message, text, parse_mode="HTML")

async def confirm_delete_handler(update, context):
    query = update.callback_query
    if not db.is_admin(query.from_user.id): return
    await query.answer(); data = query.data; parts = data.split("_", 2)
    if len(parts) >= 3:
        table = parts[2]; table = TABLE_MAP.get(table, table)
        name = parts[3] if len(parts) > 3 else ""
        if db.delete_item(table, name): await query.message.edit_text("✅ Удалено!")
        else: await query.message.edit_text("❌ Не найдено.")

# =====================================================================
# ТРИГГЕРЫ
# =====================================================================
async def newt_command(update, context):
    if not db.is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: await safe_reply(update.message, "❌ Ответьте на сообщение."); return
    if not context.args: await safe_reply(update.message, "❌ Укажите ключ: /newt прайс"); return
    kw = context.args[0].lower(); rmsg = update.message.reply_to_message
    rt = rmsg.text or rmsg.caption or ""
    rp = rmsg.photo[-1].file_id if rmsg.photo else None
    rd = rmsg.document.file_id if rmsg.document else None
    rv = rmsg.video.file_id if rmsg.video else None
    rs = rmsg.sticker.file_id if rmsg.sticker else None
    rvo = rmsg.voice.file_id if rmsg.voice else None
    ra = rmsg.audio.file_id if rmsg.audio else None
    db.save_trigger(kw, rt, rp, rd, rv, rs, rvo, ra)
    await safe_reply(update.message, f"✅ Триггер «{kw}» сохранён!")

async def delt_command(update, context):
    if not db.is_admin(update.effective_user.id): return
    if not context.args: await safe_reply(update.message, "❌ /delt ключ"); return
    if db.delete_trigger(context.args[0].lower()): await safe_reply(update.message, f"✅ «{context.args[0].lower()}» удалён.")
    else: await safe_reply(update.message, "❌ Не найден.")

async def listtr_command(update, context):
    if not db.is_admin(update.effective_user.id): return
    kws = db.get_trigger_keywords()
    if not kws: await safe_reply(update.message, "📭 Пусто."); return
    await safe_reply(update.message, "📋 Триггеры:\n" + "\n".join(f"• {k}" for k in kws))

# =====================================================================
# ГРУППОВЫЕ ОБРАБОТЧИКИ (СТАТИСТИКА + ТРИГГЕРЫ + ПРИВЕТСТВИЯ)
# =====================================================================
async def handle_group_text(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]: return
    if update.message.from_user.id == context.bot.id: return
    context.bot_data['game_chat_id'] = update.effective_chat.id
    if "group_chats" not in context.bot_data: context.bot_data["group_chats"] = set()
    context.bot_data["group_chats"].add(update.effective_chat.id)
    uid = update.effective_user.id; uname = update.effective_user.username or str(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if not db.is_admin(uid):
        old_cnt = db.cursor.execute("SELECT msg_count FROM users WHERE user_id=?", (uid,)).fetchone()
        old_cnt = old_cnt[0] if old_cnt else 0
        db.increment_msg_count(uid); db.increment_daily_msg_count(uid, today)
        db.cursor.execute("UPDATE users SET first_seen=COALESCE(first_seen,?) WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid))
        db.conn.commit()
        old_r, _ = get_rank(old_cnt); new_r, new_i = get_rank(old_cnt + 1)
        if old_r != new_r:
            await context.bot.send_message(update.effective_chat.id, f"🎉 @{uname} достиг ранга <b>{new_r}</b> {new_i}!", parse_mode="HTML")
    if update.message.text:
        text_lower = update.message.text.lower()
        triggers = db.get_all_triggers()
        for kw, rt, rp, rd, rv, rs, rvo, ra in triggers:
            if kw in text_lower:
                if rp: await update.message.reply_photo(rp, caption=rt)
                elif rd: await update.message.reply_document(rd, caption=rt)
                elif rv: await update.message.reply_video(rv, caption=rt)
                elif rs: await update.message.reply_sticker(rs)
                elif rvo: await update.message.reply_voice(rvo, caption=rt)
                elif ra: await update.message.reply_audio(ra, caption=rt)
                elif rt: await update.message.reply_text(rt)
                break
        low = update.message.text.lower()
        for w in TRIGGER_WORDS:
            if w in low: await safe_reply(update.message, random.choice(REPLY_WORDS)); break

# =====================================================================
# ЗАПУСК
# =====================================================================
async def set_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "🤖 Запустить Brandoвичок"),
        BotCommand("brand", "🛍️ Открыть меню"),
        BotCommand("statb", "📊 Топ активных"),
        BotCommand("topday", "🏆 Топ за сегодня"),
        BotCommand("rank", "⭐ Мой ранг"),
        BotCommand("ktoeto", "🆔 Инфо о пользователе"),
        BotCommand("admin", "🔧 Админ-панель (ЛС)"),
        BotCommand("startreg", "🎲 Открыть регистрацию (ЛС)"),
        BotCommand("stopreg", "🚫 Закрыть регистрацию (группа)"),
        BotCommand("openreg", "🔓 Переоткрыть регистрацию (группа)"),
        BotCommand("bingo", "🎰 Крутить бинго (админ)"),
        BotCommand("stopgame", "⏹ Остановить игру (админ)"),
        BotCommand("newt", "🆕 Новый триггер (админ)"),
        BotCommand("delt", "🗑 Удалить триггер (админ)"),
        BotCommand("listtr", "📋 Список триггеров"),
        BotCommand("skip", "⏭ Пропустить фото"),
    ])

async def error_handler(update, context):
    logger.error(f"Error: {context.error}", exc_info=context.error)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.post_init = lambda app: set_commands(app)
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("brand", brand_command))
    app.add_handler(CommandHandler("statb", stat_command))
    app.add_handler(CommandHandler("topday", topday_command))
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("ktoeto", ktoeto_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("startreg", startreg_command))
    app.add_handler(CommandHandler("stopreg", stopreg_command))
    app.add_handler(CommandHandler("openreg", openreg_command))
    app.add_handler(CommandHandler("bingo", bingo_command))
    app.add_handler(CommandHandler("stopgame", stopgame_command))
    app.add_handler(CommandHandler("newt", newt_command))
    app.add_handler(CommandHandler("delt", delt_command))
    app.add_handler(CommandHandler("listtr", listtr_command))
    app.add_handler(CommandHandler("skip", lambda u, c: safe_reply(u.message, "Нечего пропускать.")))

    app.add_handler(CallbackQueryHandler(setup_callback, pattern="^setup_"))
    app.add_handler(CallbackQueryHandler(main_callback, pattern="^(main_menu|mode_|show_|info_|stat_|shop_|exch_|vpn_|job_|bingo_|admin_|confirm_del_|check_sponsor_|stat_page_|open_menu|invite_friend)"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_text), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bingo_numbers), group=1)
    app.add_handler(MessageHandler(~filters.COMMAND & filters.ChatType.PRIVATE, admin_input_handler), group=2)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group))

    app.job_queue.run_daily(reset_daily_stats, time(0, 5, 0))

    logger.info("🚀 Brandoвичок запущен!")
    print("🚀 Brandoвичок запущен!")
    app.run_polling()
