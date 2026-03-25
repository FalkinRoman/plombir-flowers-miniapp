"""
Telegram Bot для Plombir Flowers.
Команды: /start, /help, /menu
Кнопка открытия Mini App + callback-обработка.
"""
from pathlib import Path
import html
import logging
import uuid


def _tg_html_escape(s: object) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)

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
    MessageHandler,
    filters,
    ContextTypes,
)
from backend.config import BOT_TOKEN, WEBAPP_URL, ADMIN_CHAT_ID
from backend.orders import list_recent_orders, get_order, get_orders_by_user, update_order_status
from backend.orders import update_order_moysklad
from backend.moysklad import create_customerorder, is_moysklad_ready, moysklad_not_ready_reason

log = logging.getLogger("plombir.bot")
from backend.ui_content import (
    BANNERS_DIR,
    ensure_ui_storage,
    set_ticker_text,
    add_ticker_item,
    delete_ticker_item,
    list_banners,
    add_banner,
    delete_banner,
)


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
        "📞 [ +7 981 967-28-33 ](tel:+79819672833)\n"
        "📧 [info@plombirflowers.ru](mailto:info@plombirflowers.ru)\n"
        "🌐 [plombirflowers.ru](https://plombirflowers.ru)\n"
        "✈️ [Telegram](https://t.me/plombir_flowers) | [WhatsApp](https://wa.me/79819672833)",
        parse_mode="Markdown",
    )


def _is_admin(update: Update) -> bool:
    admin_id = str(ADMIN_CHAT_ID or "").strip()
    if not admin_id:
        return False
    user_id = str(update.effective_user.id) if update.effective_user else ""
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    return admin_id in (user_id, chat_id)


async def _require_admin(update: Update) -> bool:
    if _is_admin(update):
        return True
    if update.message:
        await update.message.reply_text("⛔ Недостаточно прав.")
    return False


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


def _order_status_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Оплачен", callback_data=f"order_status:{order_id}:Оплачен"),
            InlineKeyboardButton("🌿 Флорист", callback_data=f"order_status:{order_id}:Флорист"),
        ],
        [
            InlineKeyboardButton("🚚 Курьер", callback_data=f"order_status:{order_id}:Курьер"),
            InlineKeyboardButton("📬 Доставлен", callback_data=f"order_status:{order_id}:Доставлен"),
        ],
        [InlineKeyboardButton("❌ Отменен", callback_data=f"order_status:{order_id}:Отменен")],
    ])


async def _notify_customer_status_from_bot(context: ContextTypes.DEFAULT_TYPE, order: dict):
    user_id = str(order.get("telegram_user_id") or "").strip()
    if not user_id:
        return
    status = order.get("status") or "Создан"
    status_map = {
        "Создан": "Заказ создан и ожидает оплаты.",
        "Оплачен": "Оплата получена, заказ передан флористу.",
        "Флорист": "Флорист собирает ваш заказ.",
        "Курьер": "Заказ передан курьеру.",
        "Доставлен": "Заказ доставлен. Спасибо за заказ!",
        "Отменен": "Заказ отменен.",
    }
    text = (
        f"📦 Заказ #{order.get('id')}\n"
        f"Статус: <b>{_tg_html_escape(status)}</b>\n"
        f"{_tg_html_escape(status_map.get(status, ''))}"
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception:
        pass


async def cmd_admin_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    await update.message.reply_text(
        "🛠 *Инструкция по управлению Mini App*\n\n"
        "*Бегущая строка*\n"
        "1. Полностью заменить список:\n"
        "`/ticker ТЕКСТ 1 | ТЕКСТ 2`\n"
        "2. Добавить строку в конец:\n"
        "`/ticker_add ТЕКСТ`\n"
        "3. Удалить строку по номеру:\n"
        "`/ticker_delete НОМЕР`\n\n"
        "*Баннеры*\n"
        "4. Показать текущие баннеры:\n"
        "`/banners`\n"
        "5. Добавить новый баннер:\n"
        "— просто отправьте *фото* (target=`catalog`)\n"
        "— или отправьте *фото* с подписью `/banner_add target`\n"
        "target: `catalog`, `about`, `contacts`, `payment`, `delivery` или URL\n"
        "6. Удалить баннер:\n"
        "`/banner_delete ID`\n\n"
        "*Важно*\n"
        "— порядок баннеров = порядок добавления (новые в конце)\n"
        "— если баннеров нет, в приложении показывается 1 заглушка\n"
        "— если в бегущей строке останется 0 пунктов, подставится дефолтный текст\n\n"
        "*Заказы*\n"
        "`/orders` — последние заказы и быстрые статусы",
        parse_mode="Markdown",
    )


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    orders = list_recent_orders(limit=10)
    if not orders:
        await update.message.reply_text("Заказов пока нет.")
        return
    for order in orders:
        line = (
            f"📦 Заказ #{order['id']}\n"
            f"👤 {_tg_html_escape(order.get('customer_name')) or '-'}\n"
            f"📞 {_tg_html_escape(order.get('customer_phone')) or '-'}\n"
            f"💰 {int(order.get('total') or 0)} ₽\n"
            f"Статус: <b>{_tg_html_escape(order.get('status') or 'Создан')}</b>"
        )
        await update.message.reply_text(
            line,
            parse_mode="HTML",
            reply_markup=_order_status_keyboard(order["id"]),
        )


async def cmd_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Формат: /ticker ТЕКСТ 1 | ТЕКСТ 2 | ТЕКСТ 3")
        return
    data = set_ticker_text(text)
    await update.message.reply_text(
        "✅ Бегущая строка обновлена:\n- " + "\n- ".join(data["ticker_items"])
    )


async def cmd_ticker_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Формат: /ticker_add ТЕКСТ")
        return
    data = add_ticker_item(text)
    await update.message.reply_text(
        "✅ Пункт добавлен:\n- " + "\n- ".join(data["ticker_items"])
    )


async def cmd_ticker_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /ticker_delete НОМЕР")
        return
    try:
        one_based = int(context.args[0])
        idx = one_based - 1
    except ValueError:
        await update.message.reply_text("Номер должен быть числом: /ticker_delete 2")
        return
    try:
        data = delete_ticker_item(idx)
    except IndexError:
        await update.message.reply_text("Такого пункта нет.")
        return
    await update.message.reply_text(
        "✅ Пункт удалён:\n- " + "\n- ".join(data["ticker_items"])
    )


async def cmd_banners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    banners = list_banners()
    if not banners:
        await update.message.reply_text("Баннеров пока нет.")
        return
    lines = ["🖼 Баннеры:"]
    for b in banners:
        target = b.get("target") or "catalog"
        lines.append(f"- `{b['id']}` | → {target}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_banner_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /banner_delete ID")
        return
    banner_id = context.args[0].strip()
    ok = delete_banner(banner_id)
    if ok:
        await update.message.reply_text(f"✅ Баннер `{banner_id}` удалён", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Баннер `{banner_id}` не найден", parse_mode="Markdown")


async def cmd_banner_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    await update.message.reply_text(
        "Отправьте фото с подписью:\n"
        "/banner_add target\n\n"
        "или просто фото (по умолчанию target=catalog)\n\n"
        "Пример:\n"
        "/banner_add delivery",
    )


def _parse_banner_add_caption(caption: str) -> str:
    """
    /banner_add target
    """
    payload = caption[len("/banner_add"):].strip()
    return payload or "catalog"


async def admin_banner_add_from_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    msg = update.message
    if not msg or not msg.photo:
        return
    if msg.caption and not msg.caption.lower().startswith("/banner_add"):
        return

    ensure_ui_storage()
    target = _parse_banner_add_caption(msg.caption) if msg.caption else "catalog"
    tg_file = await msg.photo[-1].get_file()
    ext = Path(tg_file.file_path or "").suffix.lower() or ".jpg"
    file_name = f"{uuid.uuid4().hex}{ext}"
    file_path = BANNERS_DIR / file_name

    await tg_file.download_to_drive(custom_path=str(file_path))
    banner = add_banner(file_path, title="", subtitle="", target=target)
    await msg.reply_text(
        f"✅ Баннер добавлен\nID: `{banner['id']}`\nTarget: `{banner['target']}`",
        parse_mode="Markdown",
    )


# ── Callback-обработка ──

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий inline-кнопок."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("order_status:"):
        if not _is_admin(update):
            await query.answer("Недостаточно прав", show_alert=True)
            return
        _, order_id_raw, next_status = query.data.split(":", 2)
        try:
            order_id = int(order_id_raw)
        except ValueError:
            await query.answer("Некорректный ID", show_alert=True)
            return
        order = update_order_status(order_id, next_status)
        if not order:
            await query.answer("Заказ не найден", show_alert=True)
            return
        # Проставляем оплату/резерв при переходе в "Оплачен" прямо из админки.
        if next_status == "Оплачен":
            from backend.orders import update_order_payment
            update_order_payment(
                order_id,
                payment_status="succeeded",
                status="Оплачен",
                inventory_state="reserved",
            )
            order = get_order(order_id) or order
            if order and is_moysklad_ready():
                try:
                    ms_id = await create_customerorder(order)
                    if ms_id:
                        update_order_moysklad(order_id, moysklad_order_id=ms_id, sync_error="")
                    else:
                        update_order_moysklad(
                            order_id,
                            sync_error="MoySklad: customerorder без id (см. логи)"[:500],
                        )
                except Exception as e:
                    log.exception("bot admin order_id=%s MoySklad create_customerorder", order_id)
                    update_order_moysklad(order_id, sync_error=str(e)[:500])
            elif order:
                reason = moysklad_not_ready_reason() or "неизвестно"
                log.warning("bot admin order_id=%s оплачен, MoySklad пропущен: %s", order_id, reason)
                update_order_moysklad(
                    order_id,
                    sync_error=f"MoySklad не настроен: {reason}"[:500],
                )
        elif next_status == "Отменен":
            from backend.orders import update_order_payment
            update_order_payment(
                order_id,
                payment_status="canceled",
                status="Отменен",
                inventory_state="none",
            )
            order = get_order(order_id) or order

        await _notify_customer_status_from_bot(context, order)
        await query.edit_message_text(
            (
                f"📦 Заказ #{order['id']}\n"
                f"👤 {_tg_html_escape(order.get('customer_name')) or '-'}\n"
                f"📞 {_tg_html_escape(order.get('customer_phone')) or '-'}\n"
                f"💰 {int(order.get('total') or 0)} ₽\n"
                f"Статус: <b>{_tg_html_escape(order.get('status') or 'Создан')}</b>"
            ),
            parse_mode="HTML",
            reply_markup=_order_status_keyboard(order["id"]),
        )
        return

    if query.data == "contacts":
        await query.message.reply_text(
            "📍 *Plombir Flowers*\n\n"
            "🏠 [ул. Кирочная, 8Б, Санкт-Петербург](https://yandex.ru/maps/?text=%D0%A1%D0%9F%D0%B1%2C%20%D1%83%D0%BB.%20%D0%9A%D0%B8%D1%80%D0%BE%D1%87%D0%BD%D0%B0%D1%8F%2C%208%D0%91)\n"
            "🕐 Каждый день с 8:30 до 22:00\n"
            "📞 [ +7 981 967-28-33 ](tel:+79819672833)\n"
            "📧 [info@plombirflowers.ru](mailto:info@plombirflowers.ru)\n"
            "🌐 [plombirflowers.ru](https://plombirflowers.ru)\n"
            "✈️ [Telegram](https://t.me/plombir_flowers) | [WhatsApp](https://wa.me/79819672833)\n\n"
            "💐 Мы делаем букеты с любовью!",
            parse_mode="Markdown",
        )

    elif query.data == "my_orders":
        user_id = str(update.effective_user.id) if update.effective_user else ""
        if not user_id:
            await query.message.reply_text("Не удалось определить пользователя.")
            return
        orders = get_orders_by_user(user_id)
        if not orders:
            await query.message.reply_text("📦 У вас пока нет заказов.")
            return
        lines = ["📦 <b>Мои заказы</b>"]
        for o in orders[:10]:
            lines.append(
                f"• #{o['id']} — <b>{_tg_html_escape(o.get('status') or 'Создан')}</b> — {int(o.get('total') or 0)} ₽"
            )
        await query.message.reply_text("\n".join(lines), parse_mode="HTML")


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
    app.add_handler(CommandHandler("admin_ui", cmd_admin_ui))
    app.add_handler(CommandHandler("ticker", cmd_ticker))
    app.add_handler(CommandHandler("ticker_add", cmd_ticker_add))
    app.add_handler(CommandHandler("ticker_delete", cmd_ticker_delete))
    app.add_handler(CommandHandler("banners", cmd_banners))
    app.add_handler(CommandHandler("banner_add", cmd_banner_add))
    app.add_handler(CommandHandler("banner_delete", cmd_banner_delete))
    app.add_handler(CommandHandler("orders", cmd_orders))

    # Фото от админа: без подписи -> catalog, с подписью /banner_add target -> заданный target
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            admin_banner_add_from_photo,
        )
    )

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Устанавливаем кнопку меню после запуска
    app.post_init = setup_menu_button

    return app
