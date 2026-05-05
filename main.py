import os
import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ChatType

TELEGRAM_BOT_TOKEN = "8643635341:AAG-H4T-Fe_LcjD4t9VAhwKLFt3bAG5P1rI"
ADMIN_ID = 7956317602  # Замените на ваш числовой ID

ASK_NAME = 1
ASK_USERNAME = 2
ASK_DESCRIPTION = 3
ASK_PHOTO = 4

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_file="shop_data.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._init_default_data()

    def _create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS shops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                username TEXT,
                description TEXT,
                photo_file_id TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS exchangers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                username TEXT,
                description TEXT,
                photo_file_id TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS vpn (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                username TEXT,
                description TEXT,
                photo_file_id TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS info_content (
                key TEXT PRIMARY KEY,
                text TEXT,
                photo_file_id TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                photo_file_id TEXT
            )
        """)
        self.conn.commit()

    def _init_default_data(self):
        for key, default_text in [('rules', '📜 Правила чата не заданы.'), ('links', '🔗 Полезные ссылки не заданы.')]:
            self.cursor.execute("INSERT OR IGNORE INTO info_content (key, text) VALUES (?, ?)", (key, default_text))
        self.conn.commit()

    # ---- Магазины ----
    def get_shops(self):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM shops")
        return self.cursor.fetchall()
    def get_shop_by_username(self, username):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM shops WHERE username = ?", (username,))
        return self.cursor.fetchone()
    def add_shop(self, name, username, description, photo_id):
        try:
            self.cursor.execute("INSERT INTO shops (name, username, description, photo_file_id) VALUES (?, ?, ?, ?)",
                                (name, username, description, photo_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def delete_shop(self, name):
        self.cursor.execute("DELETE FROM shops WHERE name = ?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    # ---- Обменники ----
    def get_exchangers(self):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM exchangers")
        return self.cursor.fetchall()
    def get_exchanger_by_username(self, username):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM exchangers WHERE username = ?", (username,))
        return self.cursor.fetchone()
    def add_exchanger(self, name, username, description, photo_id):
        try:
            self.cursor.execute("INSERT INTO exchangers (name, username, description, photo_file_id) VALUES (?, ?, ?, ?)",
                                (name, username, description, photo_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def delete_exchanger(self, name):
        self.cursor.execute("DELETE FROM exchangers WHERE name = ?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    # ---- VPN ----
    def get_vpn_list(self):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM vpn")
        return self.cursor.fetchall()
    def get_vpn_by_username(self, username):
        self.cursor.execute("SELECT name, username, description, photo_file_id FROM vpn WHERE username = ?", (username,))
        return self.cursor.fetchone()
    def add_vpn(self, name, username, description, photo_id):
        try:
            self.cursor.execute("INSERT INTO vpn (name, username, description, photo_file_id) VALUES (?, ?, ?, ?)",
                                (name, username, description, photo_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def delete_vpn(self, name):
        self.cursor.execute("DELETE FROM vpn WHERE name = ?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    # ---- Инфо ----
    def get_info(self, key):
        self.cursor.execute("SELECT text, photo_file_id FROM info_content WHERE key = ?", (key,))
        return self.cursor.fetchone()
    def update_info(self, key, text, photo_id=None):
        if photo_id:
            self.cursor.execute("UPDATE info_content SET text = ?, photo_file_id = ? WHERE key = ?", (text, photo_id, key))
        else:
            self.cursor.execute("UPDATE info_content SET text = ?, photo_file_id = NULL WHERE key = ?", (text, key))
        self.conn.commit()

    # ---- Вакансии ----
    def get_jobs(self):
        self.cursor.execute("SELECT name, description, photo_file_id FROM jobs")
        return self.cursor.fetchall()
    def get_job_by_name(self, name):
        self.cursor.execute("SELECT name, description, photo_file_id FROM jobs WHERE name = ?", (name,))
        return self.cursor.fetchone()
    def add_job(self, name, description, photo_id):
        try:
            self.cursor.execute("INSERT INTO jobs (name, description, photo_file_id) VALUES (?, ?, ?)",
                                (name, description, photo_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def delete_job(self, name):
        self.cursor.execute("DELETE FROM jobs WHERE name = ?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0

db = Database()

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛍️ Магазины", callback_data="show_shops")],
    [InlineKeyboardButton("💱 Обменники", callback_data="show_exch")],
    [InlineKeyboardButton("ℹ️ INFO", callback_data="show_info")],
    [InlineKeyboardButton("💼 Работа", callback_data="show_jobs")]
])

async def safe_delete(message):
    try:
        await message.delete()
    except:
        pass

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
async def inline_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_shops":
        items = db.get_shops()
        if not items:
            await query.message.reply_text("Список магазинов пуст.")
            await safe_delete(query.message)
            return
        kb = [[InlineKeyboardButton(i[0], callback_data=f"shop_{i[1]}")] for i in items]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        await query.message.reply_text("Выберите магазин:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
        return

    if data == "show_exch":
        items = db.get_exchangers()
        if not items:
            await query.message.reply_text("Список обменников пуст.")
            await safe_delete(query.message)
            return
        kb = [[InlineKeyboardButton(i[0], callback_data=f"exch_{i[1]}")] for i in items]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        await query.message.reply_text("Выберите обменник:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
        return

    if data == "show_jobs":
        items = db.get_jobs()
        if not items:
            await query.message.reply_text("Список вакансий пуст.")
            await safe_delete(query.message)
            return
        kb = [[InlineKeyboardButton(i[0], callback_data=f"job_{i[0]}")] for i in items]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        await query.message.reply_text("Выберите вакансию:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
        return

    if data == "show_info":
        kb = [
            [InlineKeyboardButton("📜 Правила чата", callback_data="info_rules")],
            [InlineKeyboardButton("🔗 Полезные ссылки", callback_data="info_links")],
            [InlineKeyboardButton("🛡️ Надежный VPN", callback_data="show_vpn")],
            [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
        ]
        await query.message.reply_text("Информация:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
        return

    if data == "show_vpn":
        items = db.get_vpn_list()
        if not items:
            await query.message.reply_text("Список VPN пуст.")
            await safe_delete(query.message)
            return
        kb = [[InlineKeyboardButton(i[0], callback_data=f"vpn_{i[1]}")] for i in items]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="show_info")])
        await query.message.reply_text("Выберите VPN:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
        return

    if data == "main_menu":
        await query.message.reply_text("Выберите категорию:", reply_markup=MAIN_MENU)
        await safe_delete(query.message)
        return

    if data.startswith("shop_"):
        username = data[5:]
        item = db.get_shop_by_username(username)
        if item and item[3] and item[2]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item and item[2]:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"📦 Свяжитесь с продавцом: @{item[1]}" if item else "Магазин не найден")
        await safe_delete(query.message)
        return

    if data.startswith("exch_"):
        username = data[5:]
        item = db.get_exchanger_by_username(username)
        if item and item[3] and item[2]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item and item[2]:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"💱 Свяжитесь с обменником: @{item[1]}" if item else "Обменник не найден")
        await safe_delete(query.message)
        return

    if data.startswith("vpn_"):
        username = data[4:]
        item = db.get_vpn_by_username(username)
        if item and item[3] and item[2]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item and item[2]:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"🛡️ Свяжитесь с провайдером VPN: @{item[1]}" if item else "VPN не найден")
        await safe_delete(query.message)
        return

    if data == "info_rules":
        text, photo = db.get_info('rules')
        if photo:
            await query.message.reply_photo(photo, caption=text, parse_mode="Markdown")
        else:
            await query.message.reply_text(text, parse_mode="Markdown")
        await safe_delete(query.message)
        return

    if data == "info_links":
        text, photo = db.get_info('links')
        if photo:
            await query.message.reply_photo(photo, caption=text, parse_mode="Markdown")
        else:
            await query.message.reply_text(text, parse_mode="Markdown")
        await safe_delete(query.message)
        return

    if data.startswith("job_"):
        name = data[4:]
        item = db.get_job_by_name(name)
        if item and item[2] and item[1]:
            await query.message.reply_photo(item[2], caption=item[1], parse_mode="Markdown")
        elif item and item[1]:
            await query.message.reply_text(item[1], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"💼 Вакансия: {name}")
        await safe_delete(query.message)
        return

# ========== АДМИН ПАНЕЛЬ ==========
async def admin_menu(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Только для администратора.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить магазин", callback_data="add_shop")],
        [InlineKeyboardButton("➖ Удалить магазин", callback_data="del_shop")],
        [InlineKeyboardButton("➕ Добавить обменник", callback_data="add_exch")],
        [InlineKeyboardButton("➖ Удалить обменник", callback_data="del_exch")],
        [InlineKeyboardButton("🛡️ Добавить VPN", callback_data="add_vpn")],
        [InlineKeyboardButton("🗑️ Удалить VPN", callback_data="del_vpn")],
        [InlineKeyboardButton("✏️ Правила чата", callback_data="edit_rules")],
        [InlineKeyboardButton("✏️ Полезные ссылки", callback_data="edit_links")],
        [InlineKeyboardButton("➕ Добавить вакансию", callback_data="add_job")],
        [InlineKeyboardButton("➖ Удалить вакансию", callback_data="del_job")],
        [InlineKeyboardButton("📋 Список магазинов", callback_data="list_shops")],
        [InlineKeyboardButton("📋 Список обменников", callback_data="list_exch")],
        [InlineKeyboardButton("🛡️ Список VPN", callback_data="list_vpn")],
        [InlineKeyboardButton("📋 Список вакансий", callback_data="list_jobs")],
    ])
    await update.message.reply_text("Меню управления:", reply_markup=keyboard)

async def admin_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_shop":
        await query.message.reply_text("Введите название магазина:")
        await safe_delete(query.message)
        return ASK_NAME
    if data == "del_shop":
        await query.message.reply_text("Введите название магазина для удаления:")
        await safe_delete(query.message)
        return "del_shop_name"
    if data == "add_exch":
        await query.message.reply_text("Введите название обменника:")
        await safe_delete(query.message)
        return "add_exch_name"
    if data == "del_exch":
        await query.message.reply_text("Введите название обменника для удаления:")
        await safe_delete(query.message)
        return "del_exch_name"
    if data == "add_vpn":
        await query.message.reply_text("Введите название VPN сервиса:")
        await safe_delete(query.message)
        return "add_vpn_name"
    if data == "del_vpn":
        await query.message.reply_text("Введите название VPN сервиса для удаления:")
        await safe_delete(query.message)
        return "del_vpn_name"
    if data == "edit_rules":
        await query.message.reply_text("Отправьте новый текст правил (можно с фото):")
        await safe_delete(query.message)
        return "edit_rules"
    if data == "edit_links":
        await query.message.reply_text("Отправьте новый текст полезных ссылок (можно с фото):")
        await safe_delete(query.message)
        return "edit_links"
    if data == "add_job":
        await query.message.reply_text("Введите название вакансии:")
        await safe_delete(query.message)
        return "add_job_name"
    if data == "del_job":
        await query.message.reply_text("Введите название вакансии для удаления:")
        await safe_delete(query.message)
        return "del_job_name"
    if data == "list_shops":
        items = db.get_shops()
        msg = "📋 Список магазинов:\n" + "\n".join([f"• {i[0]} — @{i[1]}" for i in items]) if items else "Пусто"
        await query.message.reply_text(msg, parse_mode="Markdown")
        await safe_delete(query.message)
        return ConversationHandler.END
    if data == "list_exch":
        items = db.get_exchangers()
        msg = "📋 Список обменников:\n" + "\n".join([f"• {i[0]} — @{i[1]}" for i in items]) if items else "Пусто"
        await query.message.reply_text(msg, parse_mode="Markdown")
        await safe_delete(query.message)
        return ConversationHandler.END
    if data == "list_vpn":
        items = db.get_vpn_list()
        msg = "🛡️ Список VPN:\n" + "\n".join([f"• {i[0]} — @{i[1]}" for i in items]) if items else "Пусто"
        await query.message.reply_text(msg, parse_mode="Markdown")
        await safe_delete(query.message)
        return ConversationHandler.END
    if data == "list_jobs":
        items = db.get_jobs()
        msg = "📋 Список вакансий:\n" + "\n".join([f"• {i[0]}" for i in items]) if items else "Пусто"
        await query.message.reply_text(msg, parse_mode="Markdown")
        await safe_delete(query.message)
        return ConversationHandler.END
    return ConversationHandler.END

# ========== ДИАЛОГИ ДОБАВЛЕНИЯ (ВСЕ ФУНКЦИИ) ==========
async def add_shop_name(update, context):
    context.user_data['shop_name'] = update.message.text
    await update.message.reply_text("Введите username продавца (без @):")
    return ASK_USERNAME

async def add_shop_username(update, context):
    context.user_data['shop_username'] = update.message.text.strip('@')
    await update.message.reply_text("Введите описание магазина:")
    return ASK_DESCRIPTION

async def add_shop_desc(update, context):
    context.user_data['shop_desc'] = update.message.text
    await update.message.reply_text("Отправьте фото магазина (или /skip):")
    return ASK_PHOTO

async def add_shop_photo(update, context):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    if db.add_shop(context.user_data['shop_name'], context.user_data['shop_username'], context.user_data['shop_desc'], photo_id):
        await update.message.reply_text("✅ Магазин добавлен.")
    else:
        await update.message.reply_text("❌ Ошибка: название уже существует.")
    return ConversationHandler.END

async def add_shop_skip(update, context):
    await update.message.reply_text("Фото пропущено.")
    return await add_shop_photo(update, context)

async def del_shop_name(update, context):
    if db.delete_shop(update.message.text):
        await update.message.reply_text("✅ Магазин удалён.")
    else:
        await update.message.reply_text("❌ Магазин не найден.")
    return ConversationHandler.END

async def add_exch_name(update, context):
    context.user_data['exch_name'] = update.message.text
    await update.message.reply_text("Введите username обменника (без @):")
    return ASK_USERNAME

async def add_exch_username(update, context):
    context.user_data['exch_username'] = update.message.text.strip('@')
    await update.message.reply_text("Введите описание обменника:")
    return ASK_DESCRIPTION

async def add_exch_desc(update, context):
    context.user_data['exch_desc'] = update.message.text
    await update.message.reply_text("Отправьте фото обменника (или /skip):")
    return ASK_PHOTO

async def add_exch_photo(update, context):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    if db.add_exchanger(context.user_data['exch_name'], context.user_data['exch_username'], context.user_data['exch_desc'], photo_id):
        await update.message.reply_text("✅ Обменник добавлен.")
    else:
        await update.message.reply_text("❌ Ошибка: название уже существует.")
    return ConversationHandler.END

async def add_exch_skip(update, context):
    await update.message.reply_text("Фото пропущено.")
    return await add_exch_photo(update, context)

async def del_exch_name(update, context):
    if db.delete_exchanger(update.message.text):
        await update.message.reply_text("✅ Обменник удалён.")
    else:
        await update.message.reply_text("❌ Обменник не найден.")
    return ConversationHandler.END

async def add_vpn_name(update, context):
    context.user_data['vpn_name'] = update.message.text
    await update.message.reply_text("Введите username провайдера VPN (без @):")
    return ASK_USERNAME

async def add_vpn_username(update, context):
    context.user_data['vpn_username'] = update.message.text.strip('@')
    await update.message.reply_text("Введите описание VPN сервиса:")
    return ASK_DESCRIPTION

async def add_vpn_desc(update, context):
    context.user_data['vpn_desc'] = update.message.text
    await update.message.reply_text("Отправьте фото для VPN (или /skip):")
    return ASK_PHOTO

async def add_vpn_photo(update, context):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    if db.add_vpn(context.user_data['vpn_name'], context.user_data['vpn_username'], context.user_data['vpn_desc'], photo_id):
        await update.message.reply_text("✅ VPN добавлен.")
    else:
        await update.message.reply_text("❌ Ошибка: название уже существует.")
    return ConversationHandler.END

async def add_vpn_skip(update, context):
    await update.message.reply_text("Фото пропущено.")
    return await add_vpn_photo(update, context)

async def del_vpn_name(update, context):
    if db.delete_vpn(update.message.text):
        await update.message.reply_text("✅ VPN удалён.")
    else:
        await update.message.reply_text("❌ VPN не найден.")
    return ConversationHandler.END

async def edit_info_handler(update, context, key, label):
    text = update.message.text or ""
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    db.update_info(key, text, photo_id)
    await update.message.reply_text(f"✅ {label} обновлены.")
    return ConversationHandler.END

async def edit_rules(update, context):
    return await edit_info_handler(update, context, 'rules', 'Правила чата')

async def edit_links(update, context):
    return await edit_info_handler(update, context, 'links', 'Полезные ссылки')

async def add_job_name(update, context):
    context.user_data['job_name'] = update.message.text
    await update.message.reply_text("Введите описание вакансии:")
    return ASK_DESCRIPTION

async def add_job_desc(update, context):
    context.user_data['job_desc'] = update.message.text
    await update.message.reply_text("Отправьте фото (или /skip):")
    return ASK_PHOTO

async def add_job_photo(update, context):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    if db.add_job(context.user_data['job_name'], context.user_data['job_desc'], photo_id):
        await update.message.reply_text("✅ Вакансия добавлена.")
    else:
        await update.message.reply_text("❌ Ошибка: название уже существует.")
    return ConversationHandler.END

async def add_job_skip(update, context):
    await update.message.reply_text("Фото пропущено.")
    return await add_job_photo(update, context)

async def del_job_name(update, context):
    if db.delete_job(update.message.text):
        await update.message.reply_text("✅ Вакансия удалена.")
    else:
        await update.message.reply_text("❌ Вакансия не найдена.")
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ========== ГРУППОВЫЕ ОБРАБОТЧИКИ ==========
async def brand_command(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Эта команда работает только в группах.")
        return
    await update.message.reply_text("Выберите категорию:", reply_markup=MAIN_MENU)

async def handle_group_text(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    if update.message.from_user.id == context.bot.id:
        return
    text = update.message.text.lower()
    trigger_words = ["магаз", "шоп", "подскажите", "обмен", "обменник", "купить"]
    if any(word in text for word in trigger_words):
        await update.message.reply_text("Вам нужна помощь? Выберите категорию:", reply_markup=MAIN_MENU)

async def bot_added_to_group(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                await update.message.reply_text(
                    "🤖 Меню магазинов, обменников, информации и работы\n\nНажмите кнопку:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Открыть меню", callback_data="main_menu")]])
                )
                return

async def start_private(update, context):
    await update.message.reply_text(
        "👋 Привет! Я бот для групп.\n\n"
        "➕ Добавьте меня в чат\n"
        "🛍️ Используйте команду /brand для вызова меню\n"
        "🔧 Администратор управляет содержимым через /admin в личных сообщениях"
    )

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_private))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("brand", brand_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_text))

    # Магазины
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^add_shop$")],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shop_name)],
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shop_username)],
            ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_shop_desc)],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, add_shop_photo), MessageHandler(filters.COMMAND & filters.Regex("^/skip$"), add_shop_skip)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^del_shop$")],
        states={"del_shop_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, del_shop_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Обменники
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^add_exch$")],
        states={
            "add_exch_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, add_exch_name)],
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_exch_username)],
            ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_exch_desc)],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, add_exch_photo), MessageHandler(filters.COMMAND & filters.Regex("^/skip$"), add_exch_skip)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^del_exch$")],
        states={"del_exch_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, del_exch_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # VPN
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^add_vpn$")],
        states={
            "add_vpn_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_name)],
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_username)],
            ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_desc)],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, add_vpn_photo), MessageHandler(filters.COMMAND & filters.Regex("^/skip$"), add_vpn_skip)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^del_vpn$")],
        states={"del_vpn_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, del_vpn_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Инфо
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^edit_rules$")],
        states={"edit_rules": [MessageHandler(filters.TEXT | filters.PHOTO, edit_rules)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^edit_links$")],
        states={"edit_links": [MessageHandler(filters.TEXT | filters.PHOTO, edit_links)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Вакансии
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^add_job$")],
        states={
            "add_job_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, add_job_name)],
            ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_job_desc)],
            ASK_PHOTO: [MessageHandler(filters.PHOTO, add_job_photo), MessageHandler(filters.COMMAND & filters.Regex("^/skip$"), add_job_skip)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^del_job$")],
        states={"del_job_name": [MessageHandler(filters.TEXT & ~filters.COMMAND, del_job_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(list_shops|list_exch|list_vpn|list_jobs)$"))
    app.add_handler(CallbackQueryHandler(inline_callback, pattern="^(show_|main_menu|shop_|exch_|vpn_|info_|job_)"))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group))

    print("Бот запущен. Все диалоги работают корректно.")
    app.run_polling()
