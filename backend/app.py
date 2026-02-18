"""
FastAPI приложение — API для Telegram Mini App «Plombir Flowers».
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from backend.config import YML_REFRESH_INTERVAL, BOT_TOKEN, ADMIN_CHAT_ID, LOW_PRIORITY_CATEGORIES
from backend.parser import fetch_and_parse
from backend.orders import init_db, create_order, get_order, get_orders_by_user


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
    items: List[OrderItem]
    total: float


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


@app.get("/api/reload")
async def reload_feed():
    """Ручное обновление фида."""
    await refresh_feed()
    return {
        "status": "ok",
        "categories_count": len(_cache["categories"]),
        "products_count": len(_cache["products"]),
    }


@app.get("/api/categories")
async def get_categories():
    """Список категорий для каталога."""
    product_cats = set()
    for p in _cache["products"]:
        for cid in p.get("category_ids", [p["category_id"]]):
            product_cats.add(cid)
    return [c for c in _cache["categories"] if c["id"] in product_cats]


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

    order_data = order.model_dump()
    # Сериализуем items в list[dict]
    order_data["items"] = [item.model_dump() for item in order.items]

    result = create_order(order_data)

    # Отправляем уведомление админу
    asyncio.create_task(_notify_admin(result))

    return {"ok": True, "order_id": result["id"]}


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

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            print(f"✅ Уведомление отправлено: заказ #{order['id']}")
    except Exception as e:
        print(f"⚠️ Ошибка отправки уведомления: {e}")


# ── Mini App (статика) ──

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "Plombir Flowers API", "docs": "/docs", "app": "/app"}
