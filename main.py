import sqlite3
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.constants import ChatType

TELEGRAM_BOT_TOKEN = "8643635341:AAG-H4T-Fe_LcjD4t9VAhwKLFt3bAG5P1rI"
ADMIN_ID = 7956317602  # Замените на ваш ID

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.conn = sqlite3.connect("shop_data.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY, name TEXT, username TEXT, description TEXT, photo TEXT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS exchangers (id INTEGER PRIMARY KEY, name TEXT, username TEXT, description TEXT, photo TEXT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS vpn (id INTEGER PRIMARY KEY, name TEXT, username TEXT, description TEXT, photo TEXT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, name TEXT, description TEXT, photo TEXT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS info (key TEXT PRIMARY KEY, text TEXT, photo TEXT)")
        self.conn.commit()
        self.cursor.execute("INSERT OR IGNORE INTO info (key, text) VALUES ('rules', '📜 Правила не заданы')")
        self.cursor.execute("INSERT OR IGNORE INTO info (key, text) VALUES ('links', '🔗 Ссылки не заданы')")
        self.conn.commit()

    def add_item(self, table, name, username, desc, photo):
        try:
            self.cursor.execute(f"INSERT INTO {table} (name, username, description, photo) VALUES (?, ?, ?, ?)", (name, username, desc, photo))
            self.conn.commit()
            return True
        except: return False
    def delete_item(self, table, name):
        self.cursor.execute(f"DELETE FROM {table} WHERE name = ?", (name,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    def get_items(self, table):
        self.cursor.execute(f"SELECT name, username, description, photo FROM {table}")
        return self.cursor.fetchall()
    def get_item(self, table, username):
        self.cursor.execute(f"SELECT name, username, description, photo FROM {table} WHERE username = ?", (username,))
        return self.cursor.fetchone()
    def update_info(self, key, text, photo):
        self.cursor.execute("UPDATE info SET text = ?, photo = ? WHERE key = ?", (text, photo, key))
        self.conn.commit()
    def get_info(self, key):
        self.cursor.execute("SELECT text, photo FROM info WHERE key = ?", (key,))
        return self.cursor.fetchone()

db = Database()

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛍️ Магазины", callback_data="show_shops")],
    [InlineKeyboardButton("💱 Обменники", callback_data="show_exch")],
    [InlineKeyboardButton("ℹ️ INFO", callback_data="show_info")],
    [InlineKeyboardButton("💼 Работа", callback_data="show_jobs")]
])

async def safe_delete(msg):
    try: await msg.delete()
    except: pass

# ========== ПОКАЗ КАТЕГОРИЙ ==========
async def show_items(update, context, table, title, back_cb, item_type):
    items = db.get_items(table)
    if not items:
        await update.callback_query.message.reply_text(f"Список {title} пуст.")
        await safe_delete(update.callback_query.message)
        return
    kb = [[InlineKeyboardButton(i[0], callback_data=f"{item_type}_{i[1]}")] for i in items]
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data=back_cb)])
    await update.callback_query.message.reply_text(f"Выберите {title}:", reply_markup=InlineKeyboardMarkup(kb))
    await safe_delete(update.callback_query.message)

# ========== ОСНОВНОЙ КОЛБЭК ==========
async def main_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_shops":
        await show_items(update, context, "shops", "магазин", "main_menu", "shop")
    elif data == "show_exch":
        await show_items(update, context, "exchangers", "обменник", "main_menu", "exch")
    elif data == "show_vpn":
        await show_items(update, context, "vpn", "VPN", "show_info", "vpn")
    elif data == "show_jobs":
        items = db.get_items("jobs")
        if not items:
            await query.message.reply_text("Список вакансий пуст.")
            await safe_delete(query.message)
            return
        kb = [[InlineKeyboardButton(i[0], callback_data=f"job_{i[0]}")] for i in items]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        await query.message.reply_text("Выберите вакансию:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
    elif data == "show_info":
        kb = [
            [InlineKeyboardButton("📜 Правила чата", callback_data="info_rules")],
            [InlineKeyboardButton("🔗 Полезные ссылки", callback_data="info_links")],
            [InlineKeyboardButton("🛡️ Надежный VPN", callback_data="show_vpn")],
            [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
        ]
        await query.message.reply_text("Информация:", reply_markup=InlineKeyboardMarkup(kb))
        await safe_delete(query.message)
    elif data == "main_menu":
        await query.message.reply_text("Выберите категорию:", reply_markup=MAIN_MENU)
        await safe_delete(query.message)
    elif data == "info_rules":
        text, photo = db.get_info('rules')
        if photo:
            await query.message.reply_photo(photo, caption=text, parse_mode="Markdown")
        else:
            await query.message.reply_text(text, parse_mode="Markdown")
        await safe_delete(query.message)
    elif data == "info_links":
        text, photo = db.get_info('links')
        if photo:
            await query.message.reply_photo(photo, caption=text, parse_mode="Markdown")
        else:
            await query.message.reply_text(text, parse_mode="Markdown")
        await safe_delete(query.message)
    elif data.startswith("shop_"):
        item = db.get_item("shops", data[5:])
        if item and item[3]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"📦 @{data[5:]}")
        await safe_delete(query.message)
    elif data.startswith("exch_"):
        item = db.get_item("exchangers", data[5:])
        if item and item[3]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"💱 @{data[5:]}")
        await safe_delete(query.message)
    elif data.startswith("vpn_"):
        item = db.get_item("vpn", data[4:])
        if item and item[3]:
            await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
        elif item:
            await query.message.reply_text(item[2], parse_mode="Markdown")
        else:
            await query.message.reply_text(f"🛡️ @{data[4:]}")
        await safe_delete(query.message)
    elif data.startswith("job_"):
        name = data[4:]
        for item in db.get_items("jobs"):
            if item[0] == name:
                if item[3]:
                    await query.message.reply_photo(item[3], caption=item[2], parse_mode="Markdown")
                else:
                    await query.message.reply_text(item[2], parse_mode="Markdown")
                break
        await safe_delete(query.message)

# ========== АДМИН МЕНЮ ==========
async def admin_menu(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Только для администратора.")
        return
    context.user_data['admin_step'] = None
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Магазин", callback_data="admin_add_shop"), InlineKeyboardButton("➖ Удалить", callback_data="admin_del_shop")],
        [InlineKeyboardButton("➕ Обменник", callback_data="admin_add_exch"), InlineKeyboardButton("➖ Удалить", callback_data="admin_del_exch")],
        [InlineKeyboardButton("➕ VPN", callback_data="admin_add_vpn"), InlineKeyboardButton("➖ Удалить", callback_data="admin_del_vpn")],
        [InlineKeyboardButton("➕ Вакансия", callback_data="admin_add_job"), InlineKeyboardButton("➖ Удалить", callback_data="admin_del_job")],
        [InlineKeyboardButton("✏️ Правила", callback_data="admin_edit_rules"), InlineKeyboardButton("✏️ Ссылки", callback_data="admin_edit_links")],
    ])
    await update.message.reply_text("Управление:", reply_markup=keyboard)

async def admin_callback(update, context):
    query = update.callback_query
    await query.answer()
    action = query.data
    await safe_delete(query.message)

    context.user_data['admin_action'] = action
    context.user_data['admin_step'] = 'wait_name'

    if action == "admin_add_shop":
        await query.message.reply_text("Введите название магазина:")
    elif action == "admin_add_exch":
        await query.message.reply_text("Введите название обменника:")
    elif action == "admin_add_vpn":
        await query.message.reply_text("Введите название VPN:")
    elif action == "admin_add_job":
        await query.message.reply_text("Введите название вакансии:")
    elif action == "admin_edit_rules":
        await query.message.reply_text("Отправьте новый текст правил (можно с фото):")
        context.user_data['admin_step'] = 'wait_info'
    elif action == "admin_edit_links":
        await query.message.reply_text("Отправьте новый текст полезных ссылок (можно с фото):")
        context.user_data['admin_step'] = 'wait_info'
    elif action == "admin_del_shop":
        await query.message.reply_text("Введите название магазина для удаления:")
        context.user_data['admin_step'] = 'wait_delete'
    elif action == "admin_del_exch":
        await query.message.reply_text("Введите название обменника для удаления:")
        context.user_data['admin_step'] = 'wait_delete'
    elif action == "admin_del_vpn":
        await query.message.reply_text("Введите название VPN для удаления:")
        context.user_data['admin_step'] = 'wait_delete'
    elif action == "admin_del_job":
        await query.message.reply_text("Введите название вакансии для удаления:")
        context.user_data['admin_step'] = 'wait_delete'

# ========== ОБРАБОТКА СООБЩЕНИЙ ОТ АДМИНА ==========
async def handle_admin_input(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if 'admin_step' not in context.user_data:
        return

    step = context.user_data['admin_step']
    action = context.user_data.get('admin_action', '')
    text = update.message.text
    photo = update.message.photo[-1].file_id if update.message.photo else None

    if step == 'wait_name':
        context.user_data['temp_name'] = text
        await update.message.reply_text("Введите username (без @):")
        context.user_data['admin_step'] = 'wait_username'
    elif step == 'wait_username':
        context.user_data['temp_username'] = text
        await update.message.reply_text("Введите описание:")
        context.user_data['admin_step'] = 'wait_desc'
    elif step == 'wait_desc':
        context.user_data['temp_desc'] = text
        await update.message.reply_text("Отправьте фото (или /skip):")
        context.user_data['admin_step'] = 'wait_photo'
    elif step == 'wait_photo':
        if text == "/skip":
            photo = None
        table = ""
        if "add_shop" in action: table = "shops"
        elif "add_exch" in action: table = "exchangers"
        elif "add_vpn" in action: table = "vpn"
        elif "add_job" in action: table = "jobs"
        if table:
            if table == "jobs":
                ok = db.add_item(table, context.user_data['temp_name'], None, context.user_data['temp_desc'], photo)
            else:
                ok = db.add_item(table, context.user_data['temp_name'], context.user_data['temp_username'], context.user_data['temp_desc'], photo)
            if ok:
                await update.message.reply_text(f"✅ Добавлено в {table}!")
            else:
                await update.message.reply_text("❌ Ошибка: возможно, такое название уже есть")
        context.user_data['admin_step'] = None
    elif step == 'wait_info':
        if "edit_rules" in action:
            db.update_info('rules', text or "", photo)
            await update.message.reply_text("✅ Правила обновлены!")
        elif "edit_links" in action:
            db.update_info('links', text or "", photo)
            await update.message.reply_text("✅ Ссылки обновлены!")
        context.user_data['admin_step'] = None
    elif step == 'wait_delete':
        table = ""
        if "del_shop" in action: table = "shops"
        elif "del_exch" in action: table = "exchangers"
        elif "del_vpn" in action: table = "vpn"
        elif "del_job" in action: table = "jobs"
        if table:
            if db.delete_item(table, text):
                await update.message.reply_text(f"✅ Удалено из {table}!")
            else:
                await update.message.reply_text("❌ Не найдено")
        context.user_data['admin_step'] = None

async def skip_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get('admin_step') == 'wait_photo':
        await handle_admin_input(update, context)
    else:
        await update.message.reply_text("Сейчас не нужно фото")

# ========== ГРУППОВЫЕ КОМАНДЫ ==========
async def brand_command(update, context):
    if update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("Только в группах.")
        return
    await update.message.reply_text("Выберите категорию:", reply_markup=MAIN_MENU)

async def handle_group_text(update, context):
    if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and update.message.from_user.id != context.bot.id:
        if any(w in update.message.text.lower() for w in ["магаз", "шоп", "подскажите", "обмен", "обменник", "купить"]):
            await update.message.reply_text("Вам нужна помощь? Выберите категорию:", reply_markup=MAIN_MENU)

async def bot_added(update, context):
    if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and update.message and update.message.new_chat_members:
        for m in update.message.new_chat_members:
            if m.id == context.bot.id:
                await update.message.reply_text("🤖 Бот готов! Используйте /brand", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Открыть меню", callback_data="main_menu")]]))
                return

async def start(update, context):
    await update.message.reply_text("👋 Я бот для групп. Добавьте меня в чат и используйте /brand\n\nАдмин: /admin")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("brand", brand_command))
    app.add_handler(CommandHandler("skip", skip_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_text))
    app.add_handler(CallbackQueryHandler(main_callback, pattern="^(show_|main_menu|info_|shop_|exch_|vpn_|job_)"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added))
    print("Бот запущен! Упрощённая система добавления без ConversationHandler.")
    app.run_polling()
