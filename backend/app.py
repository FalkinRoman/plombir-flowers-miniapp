"""
FastAPI приложение — API для Telegram Mini App «Plombir Flowers».
"""
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from backend.config import (
    YML_REFRESH_INTERVAL,
    BOT_TOKEN,
    ADMIN_CHAT_ID,
    LOW_PRIORITY_CATEGORIES,
    CATEGORY_ORDER,
    YOOKASSA_ENABLED,
    YOOKASSA_WEBHOOK_SECRET,
    SPLIT_ENABLED,
    SPLIT_MONTHS_DEFAULT,
    LOYALTY_ENABLED,
    LOYALTY_MAX_PERCENT,
    LOYALTY_RATE,
    MOYSKLAD_ENABLED,
    YANDEX_PAY_SDK_URL,
    YANDEX_PAY_MERCHANT_ID,
    YANDEX_PAY_THEME,
)
from backend.parser import fetch_and_parse
from backend.orders import (
    init_db,
    create_order,
    get_order,
    get_orders_by_user,
    update_order_payment,
    update_order_status,
    update_order_moysklad,
    list_recent_orders,
)
from backend.payments import create_payment, is_yookassa_ready, PaymentConfigError
from backend.moysklad import create_customerorder, is_moysklad_ready
from backend.ui_content import ensure_ui_storage, get_ui_content


# ── Кэш данных ──
_cache: dict = {
    "categories": [],
    "products": [],
    "loaded": False,
    "last_update": None,
}


async def refresh_feed():
    """Загрузить/обновить данные из YML-фида."""
    import datetime
    import random
    try:
        data = await fetch_and_parse()
        _cache["categories"] = data["categories"]
        products = data["products"]
        # Разделяем: основные цветы сверху, винтаж/вазы/подарки — в конце
        # Товар считается low-priority, если ВСЕ его category_ids — low-priority
        def _is_low_priority(p):
            cats = p.get("category_ids", [p["category_id"]])
            return all(c in LOW_PRIORITY_CATEGORIES for c in cats)

        main = [p for p in products if not _is_low_priority(p)]
        low = [p for p in products if _is_low_priority(p)]
        random.shuffle(main)
        random.shuffle(low)
        _cache["products"] = main + low
        _cache["loaded"] = True
        _cache["last_update"] = datetime.datetime.now().isoformat()
        print(f"✅ Фид обновлён: {len(data['categories'])} категорий, {len(data['products'])} товаров")
    except Exception as e:
        print(f"⚠️ Ошибка обновления фида: {e}")


async def scheduler():
    """Фоновая задача — обновление фида каждый час."""
    while True:
        await asyncio.sleep(YML_REFRESH_INTERVAL)
        await refresh_feed()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    ensure_ui_storage()
    await refresh_feed()
    task = asyncio.create_task(scheduler())
    yield
    # Shutdown
    task.cancel()


# ── FastAPI app ──
app = FastAPI(title="Plombir Flowers API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic модели ──

class OrderItem(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    name: str
    variant_label: Optional[str] = None
    price: float
    quantity: int
    picture: Optional[str] = None


class OrderCreate(BaseModel):
    telegram_user_id: Optional[str] = ""
    telegram_username: Optional[str] = ""
    customer_name: str
    customer_phone: str
    delivery_address: Optional[str] = ""
    delivery_date: Optional[str] = ""
    delivery_time: Optional[str] = ""
    comment: Optional[str] = ""
    card_text: Optional[str] = ""
    payment_method: Optional[str] = "manual"  # manual | card | split
    split_months: Optional[int] = None
    loyalty_points_used: Optional[float] = 0
    items: List[OrderItem]
    subtotal: Optional[float] = None
    total: float


class OrderStatusUpdate(BaseModel):
    status: str


# ── API endpoints ──

@app.get("/api/status")
async def status():
    return {
        "status": "ok",
        "loaded": _cache["loaded"],
        "last_update": _cache["last_update"],
        "categories_count": len(_cache["categories"]),
        "products_count": len(_cache["products"]),
    }


@app.get("/api/integrations/public-config")
async def integrations_public_config():
    """Публичные флаги интеграций для фронта (без секретов)."""
    return {
        "payments": {
            "yookassa_enabled": bool(YOOKASSA_ENABLED and is_yookassa_ready()),
            "split_enabled": bool(SPLIT_ENABLED and YANDEX_PAY_MERCHANT_ID),
            "split_months_default": SPLIT_MONTHS_DEFAULT,
            "methods": ["manual", "card", "split"],
            "yandex_pay_sdk_url": YANDEX_PAY_SDK_URL,
            "yandex_pay_merchant_id": YANDEX_PAY_MERCHANT_ID,
            "yandex_pay_theme": YANDEX_PAY_THEME,
        },
        "loyalty": {
            "enabled": bool(LOYALTY_ENABLED),
            "max_percent": LOYALTY_MAX_PERCENT,
            "rate": LOYALTY_RATE,
        },
        "moysklad": {
            "enabled": bool(MOYSKLAD_ENABLED),
        },
    }


@app.get("/api/reload")
async def reload_feed():
    """Ручное обновление фида."""
    await refresh_feed()
    return {
        "status": "ok",
        "categories_count": len(_cache["categories"]),
        "products_count": len(_cache["products"]),
    }


@app.get("/api/debug/categories")
async def debug_categories():
    """Дебаг: количество товаров по каждой категории."""
    cat_counts: dict[str, int] = {}
    for p in _cache["products"]:
        for cid in p.get("category_ids", [p["category_id"]]):
            cat_counts[cid] = cat_counts.get(cid, 0) + 1

    cat_names = {c["id"]: c["name"] for c in _cache["categories"]}
    result = []
    for cid, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        result.append({
            "id": cid,
            "name": cat_names.get(cid, f"(неизвестна: {cid})"),
            "products_count": count,
        })
    return result


@app.get("/api/categories")
async def get_categories():
    """Список категорий для каталога (в заданном порядке)."""
    product_cats = set()
    for p in _cache["products"]:
        for cid in p.get("category_ids", [p["category_id"]]):
            product_cats.add(cid)
    visible = [c for c in _cache["categories"] if c["id"] in product_cats]

    # Сортируем по CATEGORY_ORDER; новые/неизвестные категории — в конец
    order_map = {cid: i for i, cid in enumerate(CATEGORY_ORDER)}
    fallback = len(CATEGORY_ORDER)
    visible.sort(key=lambda c: order_map.get(c["id"], fallback))

    return visible


@app.get("/api/products")
async def get_products(
    category_id: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """Список товаров с фильтрацией."""
    items = _cache["products"]

    if category_id:
        items = [p for p in items if category_id in p.get("category_ids", [p["category_id"]])]

    if price_min is not None:
        items = [p for p in items if p["price"] and p["price"] >= price_min]

    if price_max is not None:
        items = [p for p in items if p["price"] and p["price"] <= price_max]

    if search:
        q = search.lower().strip()

        # Базовый стемминг: обрезаем типичные русские окончания для нечёткого поиска
        _RU_SUFFIXES = ("ами", "ями", "ов", "ев", "ей", "ой", "ий", "ый", "ах", "ях",
                        "ом", "ем", "ые", "ие", "ых", "их", "ую", "юю", "ая", "яя",
                        "ы", "и", "а", "я", "у", "ю", "е", "о")

        def _stem(word):
            if len(word) <= 3:
                return word
            for suf in _RU_SUFFIXES:
                if word.endswith(suf) and len(word) - len(suf) >= 2:
                    return word[:-len(suf)]
            return word

        q_stem = _stem(q)
        queries = list({q, q_stem})  # оригинал + стем

        def _text_matches(text, qs):
            """Проверяет совпадение любого из вариантов запроса."""
            t = text.lower()
            return any(qq in t for qq in qs)

        def _relevance(p):
            """0 = нет, 3 = имя начинается, 2 = имя содержит, 1 = описание/варианты."""
            name_lower = (p["name"] or "").lower()
            # Проверяем оба варианта (точный + стем)
            for qq in queries:
                if name_lower.startswith(qq):
                    return 3
            for qq in queries:
                if qq in name_lower:
                    return 2
            # Ищем в описании
            if _text_matches(p.get("description") or "", queries):
                return 1
            if _text_matches(p.get("description_html") or "", queries):
                return 1
            # Ищем в метках вариантов
            for v in p.get("variants", []):
                if _text_matches(v.get("label") or "", queries):
                    return 1
                for val in v.get("params", {}).values():
                    if _text_matches(val or "", queries):
                        return 1
            return 0

        scored = [(p, _relevance(p)) for p in items]
        items = [p for p, r in sorted(scored, key=lambda x: -x[1]) if r > 0]

    total = len(items)

    result = []
    for p in items[offset: offset + limit]:
        result.append({
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "price_max": p.get("price_max"),
            "old_price": p["old_price"],
            "category_id": p["category_id"],
            "category_ids": p.get("category_ids", [p["category_id"]]),
            "picture": p["pictures"][0] if p["pictures"] else None,
            "count": p["count"],
            "has_variants": len(p["variants"]) > 0,
        })

    return {"total": total, "offset": offset, "limit": limit, "items": result}


@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    """Полная карточка товара."""
    for p in _cache["products"]:
        if p["id"] == product_id:
            return p
    raise HTTPException(status_code=404, detail="Товар не найден")


# ── Заказы ──

@app.post("/api/orders")
async def create_new_order(order: OrderCreate):
    """Создать заказ."""
    if not order.items:
        raise HTTPException(status_code=400, detail="Корзина пуста")
    if order.total <= 0:
        raise HTTPException(status_code=400, detail="Сумма заказа должна быть больше 0")

    payment_method = (order.payment_method or "manual").strip().lower()
    if payment_method not in {"manual", "card", "split"}:
        raise HTTPException(status_code=400, detail="Некорректный способ оплаты")

    order_data = order.model_dump()
    # Сериализуем items в list[dict]
    order_data["items"] = [item.model_dump() for item in order.items]
    order_data["payment_method"] = payment_method
    order_data["payment_status"] = "pending" if payment_method in {"card", "split"} else "not_required"
    order_data["split_months"] = order.split_months or (SPLIT_MONTHS_DEFAULT if payment_method == "split" else None)
    order_data["subtotal"] = order.subtotal if order.subtotal is not None else order.total

    result = create_order(order_data)
    response = {"ok": True, "order_id": result["id"]}

    if payment_method in {"card", "split"}:
        if not (YOOKASSA_ENABLED and is_yookassa_ready()):
            response["payment"] = {
                "enabled": False,
                "status": "disabled",
                "message": "Онлайн-оплата временно недоступна: отсутствуют ключи ЮKassa",
            }
        else:
            try:
                amount = float(order.total)
                payment = await create_payment(
                    order_id=result["id"],
                    amount_rub=amount,
                    description=f"Заказ Plombir Flowers #{result['id']}",
                    customer_phone=order.customer_phone,
                    payment_method=payment_method,
                )
                payment_id = payment.get("id")
                confirmation_url = (payment.get("confirmation") or {}).get("confirmation_url")
                status_value = payment.get("status", "pending")
                update_order_payment(
                    result["id"],
                    payment_status=status_value,
                    payment_id=payment_id,
                    payment_url=confirmation_url,
                )
                response["payment"] = {
                    "enabled": True,
                    "status": status_value,
                    "payment_id": payment_id,
                    "confirmation_url": confirmation_url,
                }
            except PaymentConfigError as e:
                response["payment"] = {"enabled": False, "status": "disabled", "message": str(e)}
            except Exception as e:
                response["payment"] = {
                    "enabled": False,
                    "status": "error",
                    "message": f"Не удалось создать платеж: {e}",
                }

    # Отправляем уведомление админу
    asyncio.create_task(_notify_admin(result))

    return response


@app.get("/api/orders/{order_id}")
async def get_order_endpoint(order_id: int):
    """Получить заказ по id."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


@app.get("/api/user-orders/{telegram_user_id}")
async def get_user_orders(telegram_user_id: str):
    """Получить заказы пользователя."""
    return get_orders_by_user(telegram_user_id)


@app.get("/api/admin/orders")
async def admin_list_orders(limit: int = 30):
    """Список последних заказов для админских инструментов."""
    return list_recent_orders(limit=limit)


@app.post("/api/orders/{order_id}/status")
async def set_order_status(order_id: int, payload: OrderStatusUpdate):
    allowed = {"Создан", "Оплачен", "Флорист", "Курьер", "Доставлен", "Отменен"}
    next_status = (payload.status or "").strip()
    if next_status not in allowed:
        raise HTTPException(status_code=400, detail="Некорректный статус")
    updated = update_order_status(order_id, next_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    asyncio.create_task(_notify_customer_status(updated))
    return {"ok": True, "order": updated}


@app.get("/api/ui-content")
async def get_ui_content_endpoint():
    """Получить контент для верхнего слайдера и бегущей строки."""
    return get_ui_content()


@app.post("/api/payments/yookassa/webhook")
async def yookassa_webhook(request: Request):
    """
    Webhook от ЮKassa.
    Для безопасной настройки используем shared secret в заголовке X-Plombir-Webhook-Token.
    """
    if YOOKASSA_WEBHOOK_SECRET:
        token = request.headers.get("X-Plombir-Webhook-Token", "")
        if token != YOOKASSA_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Неверный webhook token")

    body = await request.json()
    event = body.get("event", "")
    payment_obj = body.get("object") or {}
    payment_id = payment_obj.get("id")
    status = payment_obj.get("status")
    metadata = payment_obj.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    if not order_id_raw:
        return {"ok": True}
    try:
        order_id = int(order_id_raw)
    except ValueError:
        return {"ok": True}

    if event in {"payment.succeeded", "payment.waiting_for_capture"}:
        update_order_payment(
            order_id,
            payment_status=status or "succeeded",
            payment_id=payment_id,
            status="Оплачен",
            inventory_state="reserved",
        )
        order = get_order(order_id)
        if order:
            if is_moysklad_ready():
                try:
                    ms_id = await create_customerorder(order)
                    if ms_id:
                        update_order_moysklad(order_id, moysklad_order_id=ms_id, sync_error="")
                except Exception as e:
                    update_order_moysklad(order_id, sync_error=str(e)[:500])
            asyncio.create_task(_notify_customer_status(order))
    elif event in {"payment.canceled"}:
        update_order_payment(
            order_id,
            payment_status="canceled",
            payment_id=payment_id,
            status="Отменен",
            inventory_state="none",
        )
        order = get_order(order_id)
        if order:
            asyncio.create_task(_notify_customer_status(order))
    return {"ok": True}


async def _notify_admin(order: dict):
    """Отправляем уведомление о заказе админу через Telegram Bot API."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        print("⚠️ BOT_TOKEN или ADMIN_CHAT_ID не указан — уведомление не отправлено")
        return

    import httpx

    items_text = ""
    for item in order["items"]:
        line = f"  • {item['name']}"
        if item.get("variant_label"):
            line += f" ({item['variant_label']})"
        line += f" × {item['quantity']} — {int(item['price'] * item['quantity'])} ₽"
        items_text += line + "\n"

    text = (
        f"🆕 *Новый заказ #{order['id']}*\n\n"
        f"👤 {order['customer_name']}\n"
        f"📞 {order['customer_phone']}\n"
    )
    if order.get("delivery_address"):
        text += f"📍 {order['delivery_address']}\n"
    if order.get("delivery_date"):
        text += f"📅 {order['delivery_date']}"
        if order.get("delivery_time"):
            text += f" {order['delivery_time']}"
        text += "\n"
    if order.get("card_text"):
        text += f"💌 Открытка: {order['card_text']}\n"
    if order.get("comment"):
        text += f"💬 {order['comment']}\n"

    text += f"\n📦 *Товары:*\n{items_text}\n💰 *Итого: {int(order['total'])} ₽*"

    admin_ids = [part.strip() for part in str(ADMIN_CHAT_ID).split(",") if part.strip()]
    if not admin_ids:
        return

    try:
        async with httpx.AsyncClient() as client:
            for chat_id in admin_ids:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
            print(f"✅ Уведомление отправлено: заказ #{order['id']}")
    except Exception as e:
        print(f"⚠️ Ошибка отправки уведомления: {e}")


async def _notify_customer_status(order: dict):
    tg_user_id = str(order.get("telegram_user_id") or "").strip()
    if not BOT_TOKEN or not tg_user_id:
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
        f"Статус: *{status}*\n"
        f"{status_map.get(status, '')}"
    )
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": tg_user_id, "text": text, "parse_mode": "Markdown"},
            )
    except Exception as e:
        print(f"⚠️ Ошибка отправки статуса клиенту: {e}")


# ── Mini App (статика) ──

_ROOT_DIR = Path(__file__).resolve().parent.parent
_BANNERS_DIR = _ROOT_DIR / "data" / "banners"
_FRONTEND_DIR = _ROOT_DIR / "frontend"

_BANNERS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/media/banners", StaticFiles(directory=str(_BANNERS_DIR)), name="media-banners")
app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "Plombir Flowers API", "docs": "/docs", "app": "/app"}
