"""
Telegram Bot для Plombir Flowers.
Команды: /start, /help, /menu
Кнопка открытия Mini App + callback-обработка.
"""
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    MenuButtonWebApp,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from backend.config import BOT_TOKEN, WEBAPP_URL


# ── Команды ──

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие + кнопка каталога."""
    user = update.effective_user
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🌸 Открыть каталог",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
        [
            InlineKeyboardButton("📦 Мои заказы", callback_data="my_orders"),
            InlineKeyboardButton("📞 Контакты", callback_data="contacts"),
        ],
    ])

    await update.message.reply_text(
        f"Привет, {user.first_name}! 💐\n\n"
        "Добро пожаловать в *Plombir Flowers* — цветочную студию в Санкт-Петербурге.\n\n"
        "Нажмите кнопку ниже, чтобы открыть каталог и выбрать букет:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка."""
    await update.message.reply_text(
        "🌷 *Plombir Flowers — помощь*\n\n"
        "/start — Главное меню\n"
        "/menu — Открыть каталог\n"
        "/help — Эта справка\n\n"
        "📍 Адрес: ул. Кирочная, 8Б, Санкт-Петербург\n"
        "🕐 Работаем каждый день с 8:30 до 22:00\n"
        "📞 +7 981 967-28-33\n"
        "📧 info@plombirflowers.ru",
        parse_mode="Markdown",
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню с кнопкой каталога."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🌸 Каталог",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
        [InlineKeyboardButton("📦 Мои заказы", callback_data="my_orders")],
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts")],
    ])

    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=keyboard,
    )


# ── Callback-обработка ──

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий inline-кнопок."""
    query = update.callback_query
    await query.answer()

    if query.data == "contacts":
        await query.message.reply_text(
            "📍 *Plombir Flowers*\n\n"
            "🏠 ул. Кирочная, 8Б, Санкт-Петербург\n"
            "🕐 Каждый день с 8:30 до 22:00\n"
            "📞 +7 981 967-28-33\n"
            "📧 info@plombirflowers.ru\n"
            "🌐 plombirflowers.ru\n\n"
            "💐 Мы делаем букеты с любовью!",
            parse_mode="Markdown",
        )

    elif query.data == "my_orders":
        await query.message.reply_text(
            "📦 *Мои заказы*\n\n"
            "Для просмотра заказов откройте каталог и перейдите в корзину.\n"
            "История заказов будет доступна в ближайшем обновлении! 🚀",
            parse_mode="Markdown",
        )


# ── Настройка ──

async def setup_menu_button(app: Application):
    """Устанавливаем кнопку Mini App в меню бота."""
    await app.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🌸 Каталог",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )


def create_bot() -> Application:
    """Создаёт и настраивает бота."""
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Устанавливаем кнопку меню после запуска
    app.post_init = setup_menu_button

    return app
