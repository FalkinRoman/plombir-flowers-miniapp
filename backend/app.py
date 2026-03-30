"""
FastAPI приложение — API для Telegram Mini App «Plombir Flowers».
"""
import asyncio
import html
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
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
    SPLIT_PAYMENT_METHOD_DATA_TYPE,
    LOYALTY_ENABLED,
    LOYALTY_MAX_PERCENT,
    LOYALTY_RATE,
    MOYSKLAD_ENABLED,
    MOYSKLAD_DELIVERY_PRODUCT_CODE,
    TILDA_MOYSKLAD_WEBHOOK_ENABLED,
    TILDA_MOYSKLAD_WEBHOOK_TOKEN,
    YANDEX_PAY_SDK_URL,
    YANDEX_PAY_MERCHANT_ID,
    YANDEX_PAY_THEME,
    MOYSKLAD_TOKEN,
    ADMIN_BOOTSTRAP_EMAIL,
    ADMIN_BOOTSTRAP_PASSWORD,
    ADMIN_SESSION_TTL_SECONDS,
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
    authenticate_admin,
    create_admin_session,
    get_admin_by_session,
    delete_admin_session,
    create_or_update_admin_user,
    list_product_mappings,
    upsert_product_mapping,
    delete_product_mapping,
    replace_ms_assortment_cache,
    search_ms_assortment_cache,
    list_order_telegram_users,
)
from backend.payments import create_payment, is_yookassa_ready, PaymentConfigError
from backend.moysklad import create_customerorder, is_moysklad_ready, moysklad_not_ready_reason
from backend.ui_content import ensure_ui_storage, get_ui_content

log = logging.getLogger("plombir")


def _tg_html_escape(s: object) -> str:
    """Экранирование для Telegram HTML (без parse_mode Markdown — он ломается на _, * в ФИО/адресе)."""
    return html.escape(str(s if s is not None else ""), quote=False)


async def _telegram_send_message(chat_id: str, text: str, *, parse_mode: str = "HTML") -> bool:
    """Отправка в Telegram с таймаутом; True если ок."""
    if not BOT_TOKEN or not chat_id:
        return False
    import httpx

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            if r.status_code >= 400:
                log.warning("Telegram sendMessage HTTP %s: %s", r.status_code, (r.text or "")[:300])
                return False
            return True
    except Exception as e:
        log.warning("Telegram sendMessage error: %s", e)
        return False

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
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    logging.getLogger("plombir").setLevel(logging.INFO)
    logging.getLogger("plombir.moysklad").setLevel(logging.INFO)
    init_db()
    if (ADMIN_BOOTSTRAP_PASSWORD or "").strip():
        try:
            create_or_update_admin_user(
                email=ADMIN_BOOTSTRAP_EMAIL,
                password=ADMIN_BOOTSTRAP_PASSWORD,
                role="admin",
                is_active=True,
            )
            log.info("Admin bootstrap checked for %s", ADMIN_BOOTSTRAP_EMAIL)
        except Exception as e:
            log.warning("Admin bootstrap failed: %s", e)
    else:
        log.warning("ADMIN_BOOTSTRAP_PASSWORD не задан — вход в админку отключен до создания пользователя.")
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
    product_code: Optional[str] = None
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
    delivery_type: Optional[str] = ""
    contact_method: Optional[str] = ""
    recipient_name: Optional[str] = ""
    recipient_phone: Optional[str] = ""
    courier_comment: Optional[str] = ""
    telegram_nickname: Optional[str] = ""
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


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminMappingUpsertRequest(BaseModel):
    tilda_key: str
    ms_href: str
    ms_type: str = "assortment"
    ms_id: Optional[str] = None
    ms_name: Optional[str] = None
    note: Optional[str] = None


class AdminBroadcastRequest(BaseModel):
    text: str
    parse_mode: str = "HTML"
    dry_run: bool = True
    limit: Optional[int] = None


def _extract_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def _require_admin(request: Request) -> dict:
    token = _extract_bearer_token(request)
    admin = get_admin_by_session(token)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin auth required")
    return admin


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
            # Виджеты/badge: нужен merchant id. Оплата сплитом всё равно через ЮKassa (create_payment).
            "split_enabled": bool(SPLIT_ENABLED and YANDEX_PAY_MERCHANT_ID),
            "split_months_default": SPLIT_MONTHS_DEFAULT,
            # Что реально уходит в ЮKassa для split (для отладки / согласования с кабинетом)
            "split_payment_method_data": SPLIT_PAYMENT_METHOD_DATA_TYPE
            if SPLIT_PAYMENT_METHOD_DATA_TYPE in {"yandex_pay", "bank_card"}
            else "yandex_pay",
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


def _apply_catalog_sort(items: list, sort: str, *, search_active: bool) -> None:
    """
    Сортировка как в каталоге Tilda: цена, название, порядок фида.
    При активном поиске и sort=default сохраняем порядок по релевантности.
    Вторичный ключ id — стабильный порядок при одинаковой цене и не мутируем кэш.
    """
    s = (sort or "price_asc").strip().lower()
    allowed = {
        "default", "price_asc", "price_desc",
        "name_asc", "name_desc", "newest", "oldest",
    }
    if s not in allowed:
        s = "price_asc"
    if search_active and s == "default":
        return
    if s == "default":
        return

    def _price_key(p):
        pr = p.get("price")
        if pr is None:
            price = float("inf")
        else:
            try:
                price = float(pr)
            except (TypeError, ValueError):
                price = float("inf")
        sid = str(p.get("id") or "")
        return (price, sid)

    def _name_key(p):
        return ((p.get("name") or "").lower(), str(p.get("id") or ""))

    def _order_key(p):
        return int(p.get("catalog_order", 0))

    if s == "price_asc":
        items.sort(key=_price_key)
    elif s == "price_desc":
        items.sort(key=_price_key, reverse=True)
    elif s == "name_asc":
        items.sort(key=_name_key)
    elif s == "name_desc":
        items.sort(key=_name_key, reverse=True)
    elif s == "newest":
        items.sort(key=_order_key, reverse=True)
    elif s == "oldest":
        items.sort(key=_order_key)


@app.get("/api/products")
async def get_products(
    category_id: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    search: Optional[str] = None,
    sort: str = "price_asc",
    limit: int = 20,
    offset: int = 0,
):
    """Список товаров с фильтрацией и сортировкой (как на сайте Tilda)."""
    # Всегда копия: иначе sort() мутирует _cache["products"] и порядок ломается между запросами.
    items = list(_cache["products"])

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

    _apply_catalog_sort(items, sort, search_active=bool(search and search.strip()))

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
            "code": p.get("code") or p["id"],
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


def _to_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=1) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


@app.post("/api/integrations/tilda-moysklad/webhook")
async def tilda_moysklad_webhook(request: Request):
    """
    Совместимость со старой кастомной интеграцией Tilda -> МойСклад.
    Принимаем payload в стиле request.php и создаем заказ в нашей БД + МойСклад.
    """
    if not TILDA_MOYSKLAD_WEBHOOK_ENABLED:
        raise HTTPException(status_code=404, detail="Webhook disabled")

    if TILDA_MOYSKLAD_WEBHOOK_TOKEN:
        token = request.headers.get("Token", "")
        if token != TILDA_MOYSKLAD_WEBHOOK_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid webhook token")

    payload = await request.json()
    payment = payload.get("payment") or {}
    products = payment.get("products") or []
    if not isinstance(products, list) or not products:
        raise HTTPException(status_code=400, detail="No products in payload")

    items = []
    for p in products:
        if not isinstance(p, dict):
            continue
        code = (
            p.get("externalid")
            or p.get("external_id")
            or p.get("code")
            or p.get("sku")
            or p.get("id")
            or p.get("name")
        )
        items.append({
            "product_id": str(p.get("id") or code or ""),
            "variant_id": p.get("variant_id"),
            "product_code": str(code or ""),
            "name": str(p.get("name") or "Товар"),
            "variant_label": p.get("variant_label"),
            "price": _to_float(p.get("price"), 0.0),
            "quantity": _to_int(p.get("quantity"), 1),
            "picture": p.get("picture"),
        })

    # Доставка как отдельная позиция (как в старом php-скрипте), если есть код.
    delivery_price = _to_float(payment.get("delivery_price"), 0.0)
    if delivery_price > 0 and MOYSKLAD_DELIVERY_PRODUCT_CODE:
        items.append({
            "product_id": f"delivery-{MOYSKLAD_DELIVERY_PRODUCT_CODE}",
            "variant_id": None,
            "product_code": MOYSKLAD_DELIVERY_PRODUCT_CODE,
            "name": "Доставка",
            "variant_label": None,
            "price": delivery_price,
            "quantity": 1,
            "picture": None,
        })

    total = _to_float(payment.get("total"), 0.0) or _to_float(payment.get("subtotal"), 0.0)
    if total <= 0:
        total = sum(_to_float(i.get("price")) * _to_int(i.get("quantity"), 1) for i in items)

    order_data = {
        "telegram_user_id": "",
        "telegram_username": "",
        "customer_name": str(payload.get("name") or payload.get("customer_name") or "Клиент"),
        "customer_phone": str(payload.get("phone") or payload.get("customer_phone") or ""),
        "delivery_address": str(payload.get("address") or ""),
        "delivery_date": str(payload.get("delivery_date") or payload.get("Дата_доставки") or ""),
        "delivery_time": str(payload.get("time") or ""),
        "delivery_type": str(payment.get("delivery") or payload.get("delivery_type") or "Курьер"),
        "contact_method": str(payload.get("order_apply") or payload.get("contact_method") or "Telegram"),
        "recipient_name": str(payload.get("receiver_name") or payload.get("recipient_name") or ""),
        "recipient_phone": str(payload.get("receiver_phone") or payload.get("recipient_phone") or ""),
        "courier_comment": str(payload.get("couriercomment") or payload.get("courier_comment") or ""),
        "telegram_nickname": str(payload.get("telegram_name") or payload.get("telegram_nickname") or ""),
        "comment": str(payload.get("comment") or ""),
        "card_text": str(payload.get("cart") or payload.get("card_text") or ""),
        "items": items,
        "subtotal": _to_float(payment.get("subtotal"), total),
        "total": total,
        "status": "Создан",
        "payment_method": "manual",
        "payment_status": "not_required",
    }
    created = create_order(order_data)

    ms_id = None
    ms_error = ""
    if is_moysklad_ready():
        try:
            ms_id = await create_customerorder(created)
            if ms_id:
                ms_error = ""
            else:
                ms_error = "MoySklad: customerorder без id (см. логи)"[:500]
        except Exception as e:
            log.exception("tilda_moysklad_webhook order_id=%s MoySklad", created["id"])
            ms_error = str(e)[:500]
    else:
        ms_error = f"MoySklad не настроен: {moysklad_not_ready_reason()}"[:500]
        log.warning("tilda_moysklad_webhook order_id=%s: %s", created["id"], ms_error)
    update_order_moysklad(created["id"], moysklad_order_id=ms_id, sync_error=ms_error)

    return {"ok": True, "order_id": created["id"], "moysklad_order_id": ms_id}


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
async def admin_list_orders(request: Request, limit: int = 30):
    """Список последних заказов для админских инструментов."""
    _require_admin(request)
    return list_recent_orders(limit=limit)


@app.post("/api/admin/auth/login")
async def admin_auth_login(payload: AdminLoginRequest):
    user = authenticate_admin(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_admin_session(user["id"], ttl_seconds=ADMIN_SESSION_TTL_SECONDS)
    return {"ok": True, "token": token, "user": user, "ttl": ADMIN_SESSION_TTL_SECONDS}


@app.post("/api/admin/auth/logout")
async def admin_auth_logout(request: Request):
    admin = _require_admin(request)
    delete_admin_session(admin.get("token") or "")
    return {"ok": True}


@app.get("/api/admin/auth/me")
async def admin_auth_me(request: Request):
    admin = _require_admin(request)
    return {"ok": True, "user": {"id": admin["id"], "email": admin["email"], "role": admin["role"]}}


@app.get("/api/admin/mappings")
async def admin_mappings_list(request: Request, limit: int = 300, q: str = ""):
    _require_admin(request)
    return list_product_mappings(limit=limit, search=q)


@app.post("/api/admin/mappings")
async def admin_mappings_upsert(request: Request, payload: AdminMappingUpsertRequest):
    admin = _require_admin(request)
    try:
        upsert_product_mapping(
            tilda_key=payload.tilda_key,
            ms_href=payload.ms_href,
            ms_type=payload.ms_type,
            ms_id=payload.ms_id,
            ms_name=payload.ms_name,
            note=payload.note,
            updated_by=admin["email"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.delete("/api/admin/mappings/{tilda_key}")
async def admin_mappings_delete(request: Request, tilda_key: str):
    _require_admin(request)
    delete_product_mapping(tilda_key)
    return {"ok": True}


@app.post("/api/admin/feed/refresh")
async def admin_feed_refresh(request: Request):
    """Принудительно перечитать YML-фид (как при старте сервера и по расписанию)."""
    _require_admin(request)
    await refresh_feed()
    return {
        "ok": True,
        "loaded": bool(_cache.get("loaded")),
        "categories_count": len(_cache.get("categories") or []),
        "products_count": len(_cache.get("products") or []),
        "last_update": _cache.get("last_update"),
    }


@app.get("/api/admin/feed-products")
async def admin_feed_products(
    request: Request,
    q: str = "",
    limit: int = 300,
    unmapped_only: bool = False,
):
    _require_admin(request)
    lim = max(1, min(limit, 2000))
    needle = (q or "").strip().lower()
    mappings = {m.get("tilda_key"): m for m in list_product_mappings(limit=5000)}
    rows = []
    for p in _cache["products"]:
        variants = p.get("variants") or []
        if variants:
            for v in variants:
                key = str(v.get("code") or v.get("id") or "").strip()
                if not key:
                    continue
                name = f"{p.get('name')} - {v.get('label') or ''}".strip()
                mapped = mappings.get(key)
                if unmapped_only and mapped:
                    continue
                if needle and needle not in name.lower() and needle not in key.lower():
                    continue
                rows.append({
                    "name": name,
                    "tilda_key": key,
                    "base_product_id": p.get("id"),
                    "mapped": bool(mapped),
                    "mapping": mapped,
                })
        else:
            key = str(p.get("code") or p.get("id") or "").strip()
            if not key:
                continue
            mapped = mappings.get(key)
            if unmapped_only and mapped:
                continue
            name = str(p.get("name") or "")
            if needle and needle not in name.lower() and needle not in key.lower():
                continue
            rows.append({
                "name": name,
                "tilda_key": key,
                "base_product_id": p.get("id"),
                "mapped": bool(mapped),
                "mapping": mapped,
            })
        if len(rows) >= lim:
            break
    return rows


@app.post("/api/admin/moysklad/cache/refresh")
async def admin_refresh_moysklad_cache(request: Request):
    _require_admin(request)
    if not (MOYSKLAD_TOKEN or "").strip():
        raise HTTPException(status_code=400, detail="MOYSKLAD_TOKEN пуст")
    import httpx

    headers = {
        "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
        "Accept": "application/json;charset=utf-8",
    }
    rows: list[dict] = []
    offset = 0
    limit = 1000
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            url = f"https://api.moysklad.ru/api/remap/1.2/entity/assortment?limit={limit}&offset={offset}"
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"MoySklad HTTP {resp.status_code}")
            data = resp.json() or {}
            chunk = data.get("rows") or []
            for r in chunk:
                meta = (r or {}).get("meta") or {}
                rows.append({
                    "ms_id": str((r or {}).get("id") or ""),
                    "ms_href": str(meta.get("href") or ""),
                    "ms_type": str(meta.get("type") or "assortment"),
                    "name": str((r or {}).get("name") or ""),
                    "code": str((r or {}).get("code") or ""),
                    "external_code": str((r or {}).get("externalCode") or ""),
                    "archived": bool((r or {}).get("archived")),
                })
            if len(chunk) < limit:
                break
            offset += limit
    replace_ms_assortment_cache(rows)
    return {"ok": True, "count": len(rows)}


@app.get("/api/admin/moysklad/cache/search")
async def admin_search_moysklad_cache(request: Request, q: str = "", limit: int = 100):
    _require_admin(request)
    return search_ms_assortment_cache(query=q, limit=limit)


@app.post("/api/admin/broadcast")
async def admin_broadcast(request: Request, payload: AdminBroadcastRequest):
    _require_admin(request)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой текст")
    requested_limit = payload.limit if payload.limit is not None else 20000
    users = list_order_telegram_users(limit=max(1, min(int(requested_limit), 20000)))
    sent = 0
    failed = 0
    sample = []
    admin_test_sent = False
    admin_test_error = ""
    for row in users:
        chat_id = str(row.get("telegram_user_id") or "").strip()
        if not chat_id:
            continue
        if payload.dry_run:
            if len(sample) < 20:
                sample.append(chat_id)
            continue
        ok = await _telegram_send_message(chat_id, text, parse_mode=payload.parse_mode or "HTML")
        if ok:
            sent += 1
        else:
            failed += 1
    if payload.dry_run:
        admin_ids = [part.strip() for part in str(ADMIN_CHAT_ID).split(",") if part.strip()]
        admin_target = admin_ids[0] if admin_ids else ""
        if admin_target:
            preview = (
                "🧪 <b>Тест рассылки (dry-run)</b>\n"
                "Это предпросмотр для админа. Массовой отправки не было.\n\n"
                f"{text}"
            )
            ok = await _telegram_send_message(admin_target, preview, parse_mode=payload.parse_mode or "HTML")
            admin_test_sent = bool(ok)
            if not ok:
                admin_test_error = "Не удалось отправить тест админу"
        else:
            admin_test_error = "ADMIN_CHAT_ID не задан — тест админу пропущен"
        return {
            "ok": True,
            "mode": "dry_run",
            "targets": len(users),
            "sample_ids": sample,
            "admin_test_sent": admin_test_sent,
            "admin_test_error": admin_test_error,
        }
    return {"ok": True, "mode": "send", "targets": len(users), "sent": sent, "failed": failed}


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
            log.warning("yookassa_webhook отклонён: неверный X-Plombir-Webhook-Token")
            raise HTTPException(status_code=403, detail="Неверный webhook token")

    body = await request.json()
    event = body.get("event", "")
    payment_obj = body.get("object") or {}
    payment_id = payment_obj.get("id")
    status = payment_obj.get("status")
    metadata = payment_obj.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    log.info(
        "yookassa_webhook event=%s payment_id=%s status=%s metadata_order_id=%s",
        event,
        payment_id,
        status,
        order_id_raw,
    )
    if not order_id_raw:
        log.warning(
            "yookassa_webhook: нет metadata.order_id — синхронизация с БД/MoySklad пропущена "
            "(payment_id=%s)",
            payment_id,
        )
        return {"ok": True}
    try:
        order_id = int(order_id_raw)
    except ValueError:
        log.warning(
            "yookassa_webhook: metadata.order_id не число: %r (payment_id=%s)",
            order_id_raw,
            payment_id,
        )
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
                    else:
                        msg = "MoySklad: customerorder без id в ответе (см. логи plombir.moysklad)"
                        log.error("order_id=%s yookassa_webhook: %s", order_id, msg)
                        update_order_moysklad(order_id, sync_error=msg[:500])
                except Exception as e:
                    log.exception(
                        "order_id=%s yookassa_webhook: MoySklad create_customerorder",
                        order_id,
                    )
                    update_order_moysklad(order_id, sync_error=str(e)[:500])
            else:
                reason = moysklad_not_ready_reason() or "неизвестно"
                log.warning(
                    "order_id=%s оплачен, MoySklad пропущен: %s",
                    order_id,
                    reason,
                )
                update_order_moysklad(
                    order_id,
                    sync_error=f"MoySklad не настроен: {reason}"[:500],
                )
            asyncio.create_task(_notify_customer_status(order))
            asyncio.create_task(_notify_admin_payment_paid(order))
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
    else:
        log.info("yookassa_webhook: событие не обрабатываем явно: %s", event)
    return {"ok": True}


async def _notify_admin(order: dict):
    """Отправляем уведомление о заказе админу через Telegram Bot API (HTML — без срыва от _, * в текстах)."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        log.warning("BOT_TOKEN или ADMIN_CHAT_ID не указан — уведомление админу пропущено")
        return

    items_text = ""
    for item in order["items"]:
        line = f"  • {_tg_html_escape(item.get('name'))}"
        if item.get("variant_label"):
            line += f" ({_tg_html_escape(item['variant_label'])})"
        line += f" × {item['quantity']} — {int(item['price'] * item['quantity'])} ₽"
        items_text += line + "\n"

    text = (
        f"🆕 <b>Новый заказ #{order['id']}</b>\n\n"
        f"👤 {_tg_html_escape(order.get('customer_name'))}\n"
        f"📞 {_tg_html_escape(order.get('customer_phone'))}\n"
    )
    if order.get("delivery_address"):
        text += f"📍 {_tg_html_escape(order['delivery_address'])}\n"
    if order.get("delivery_type"):
        text += f"🚚 Тип доставки: {_tg_html_escape(order['delivery_type'])}\n"
    if order.get("delivery_date"):
        text += f"📅 {_tg_html_escape(order['delivery_date'])}"
        if order.get("delivery_time"):
            text += f" {_tg_html_escape(order['delivery_time'])}"
        text += "\n"
    if order.get("recipient_name"):
        text += f"🎁 Получатель: {_tg_html_escape(order['recipient_name'])}\n"
    if order.get("recipient_phone"):
        text += f"📲 Тел. получателя: {_tg_html_escape(order['recipient_phone'])}\n"
    if order.get("contact_method"):
        text += f"☎️ Связь: {_tg_html_escape(order['contact_method'])}\n"
    if order.get("courier_comment"):
        text += f"🛵 Курьеру: {_tg_html_escape(order['courier_comment'])}\n"
    if order.get("card_text"):
        text += f"💌 Открытка: {_tg_html_escape(order['card_text'])}\n"
    if order.get("comment"):
        text += f"💬 {_tg_html_escape(order['comment'])}\n"

    text += f"\n📦 <b>Товары:</b>\n{items_text}\n💰 <b>Итого: {int(order['total'])} ₽</b>"

    admin_ids = [part.strip() for part in str(ADMIN_CHAT_ID).split(",") if part.strip()]
    if not admin_ids:
        return

    ok_any = False
    for chat_id in admin_ids:
        if await _telegram_send_message(chat_id, text):
            ok_any = True
    if ok_any:
        log.info("Уведомление админу отправлено: заказ #%s", order['id'])
    else:
        log.warning("Не удалось отправить уведомление админу по заказу #%s", order['id'])


async def _notify_admin_payment_paid(order: dict):
    """Короткая отбивка админу после успешной оплаты (ЮKassa webhook)."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    oid = order.get("id")
    total = order.get("total")
    pm = _tg_html_escape(order.get("payment_method") or "")
    text = (
        f"✅ <b>Оплата получена</b> · заказ <b>#{oid}</b>\n"
        f"Сумма: {int(total or 0)} ₽ · способ: {pm or '—'}"
    )
    admin_ids = [part.strip() for part in str(ADMIN_CHAT_ID).split(",") if part.strip()]
    for chat_id in admin_ids:
        await _telegram_send_message(chat_id, text)


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
        f"Статус: <b>{_tg_html_escape(status)}</b>\n"
        f"{_tg_html_escape(status_map.get(status, ''))}"
    )
    await _telegram_send_message(tg_user_id, text)


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


@app.get("/admin")
async def admin_root():
    return RedirectResponse(url="/app/admin.html")
