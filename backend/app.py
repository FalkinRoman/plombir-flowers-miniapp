"""
FastAPI приложение — API для Telegram Mini App «Plombir Flowers».
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional

from backend.config import YML_REFRESH_INTERVAL
from backend.parser import fetch_and_parse


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
    try:
        data = await fetch_and_parse()
        _cache["categories"] = data["categories"]
        _cache["products"] = data["products"]
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
    # Возвращаем только те, где есть товары
    product_cats = set(p["category_id"] for p in _cache["products"])
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
        items = [p for p in items if p["category_id"] == category_id]

    if price_min is not None:
        items = [p for p in items if p["price"] and p["price"] >= price_min]

    if price_max is not None:
        items = [p for p in items if p["price"] and p["price"] <= price_max]

    if search:
        q = search.lower()
        items = [p for p in items if q in (p["name"] or "").lower()]

    total = len(items)

    # Для списка — отдаём урезанную версию (без description_html, без вариантов)
    result = []
    for p in items[offset: offset + limit]:
        result.append({
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "price_max": p.get("price_max"),
            "old_price": p["old_price"],
            "category_id": p["category_id"],
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


# ── Mini App (статика) ──

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "Plombir Flowers API", "docs": "/docs", "app": "/app"}
