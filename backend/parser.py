"""
Парсер YML-фида Тильды.
Загружает, парсит, группирует варианты, чистит описания.
"""
import re
import httpx
from lxml import etree
from typing import Optional
from collections import defaultdict
from backend.config import (
    YML_FEED_URL, HIDDEN_CATEGORIES, BOILERPLATE_TEXTS,
    TILDA_STORE_API, TILDA_STORE_ALL_UID, TILDA_STORE_RECID,
)


def clean_html(html: str) -> str:
    """Убираем HTML-теги, оставляем чистый текст."""
    if not html:
        return ""
    text = html.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = re.sub(r'<li[^>]*>', "• ", text)
    text = text.replace("</li>", "\n")
    text = text.replace("<ul>", "").replace("</ul>", "")
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_description(desc: str) -> str:
    """Чистим HTML + убираем шаблонный текст."""
    text = clean_html(desc)
    for boilerplate in BOILERPLATE_TEXTS:
        idx = text.find(boilerplate[:20])
        if idx != -1:
            text = text[:idx].strip()
    return text


def _text(el, tag: str) -> Optional[str]:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _float(el, tag: str) -> Optional[float]:
    v = _text(el, tag)
    return float(v) if v else None


def _int(el, tag: str) -> Optional[int]:
    v = _text(el, tag)
    return int(v) if v else None


async def _fetch_partuids_map(yml_category_ids: list[str]) -> dict[str, list[str]]:
    """
    Получает маппинг product_uid → [category_ids] через Tilda Store API.
    Опрашивает все категории (включая скрытые), чтобы собрать полный partuids.
    Tilda API возвращает partuids (все категории товара), в отличие от YML (одна).
    """
    import time
    import json as _json

    # Опрашиваем все категории из YML-фида + мета-категорию "Все"
    cat_ids_to_fetch = list(set(yml_category_ids + [TILDA_STORE_ALL_UID]))

    mapping: dict[str, list[str]] = {}

    def _process_product(p):
        uid = str(p.get("uid", ""))
        partuids_raw = p.get("partuids", "")
        if not uid or not partuids_raw:
            return
        # partuids приходит как строка "[id1,id2,...]" или список
        if isinstance(partuids_raw, str):
            cat_ids = [c.strip() for c in partuids_raw.strip("[]").split(",") if c.strip()]
        else:
            cat_ids = [str(c) for c in partuids_raw]
        # Фильтруем скрытые категории
        cat_ids = [c for c in cat_ids if c not in HIDDEN_CATEGORIES]
        if not cat_ids:
            return
        # Сохраняем самый полный список категорий
        if uid not in mapping or len(cat_ids) > len(mapping[uid]):
            mapping[uid] = cat_ids

        # Также маппим edition uid-ы (варианты) на те же категории
        editions = p.get("editions")
        if editions:
            if isinstance(editions, str):
                try:
                    editions = _json.loads(editions)
                except Exception:
                    editions = []
            for ed in editions:
                ed_uid = str(ed.get("uid", ""))
                if ed_uid:
                    if ed_uid not in mapping or len(cat_ids) > len(mapping[ed_uid]):
                        mapping[ed_uid] = cat_ids

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for cat_id in cat_ids_to_fetch:
                try:
                    params = {
                        "storepartuid": cat_id,
                        "recid": TILDA_STORE_RECID,
                        "c": str(int(time.time())),
                        "getparts": "true",
                        "getoptions": "true",
                        "slice": "1",
                        "size": "1000",
                    }
                    resp = await client.get(TILDA_STORE_API, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for p in data.get("products", []):
                            _process_product(p)
                except Exception:
                    pass  # Пропускаем ошибки отдельных категорий

        print(f"📦 Tilda API: маппинг partuids для {len(mapping)} товаров/вариантов "
              f"(опрошено {len(cat_ids_to_fetch)} категорий)")
        return mapping
    except Exception as e:
        print(f"⚠️ Не удалось загрузить partuids из Tilda API: {e}")
        return {}


async def fetch_and_parse() -> dict:
    """
    Загружает YML-фид, парсит, группирует варианты.
    Обогащает category_ids из Tilda Store API (partuids).
    Возвращает {"categories": [...], "products": [...]}.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(YML_FEED_URL)
        resp.raise_for_status()

    root = etree.fromstring(resp.content)
    shop = root.find("shop")

    # --- Категории ---
    categories = []
    for cat in shop.findall(".//categories/category"):
        cat_id = cat.get("id")
        if cat_id in HIDDEN_CATEGORIES:
            continue
        categories.append({
            "id": cat_id,
            "name": (cat.text or "").strip(),
        })

    # --- Товары (сырые) — загружаем ВСЕ, фильтрация по категориям позже ---
    raw_offers = []
    for offer in shop.findall(".//offers/offer"):
        cat_id = _text(offer, "categoryId")

        raw = {
            "id": offer.get("id"),
            "name": _text(offer, "name"),
            "description": _text(offer, "description"),
            "price": _float(offer, "price"),
            "old_price": _float(offer, "oldprice"),
            "code": _text(offer, "vendorCode") or offer.get("id"),
            "category_id": cat_id,
            "url": _text(offer, "url"),
            "pictures": [pic.text.strip() for pic in offer.findall("picture") if pic.text],
            "count": _int(offer, "count"),
            "params": {},
        }
        for param in offer.findall("param"):
            param_name = param.get("name", "")
            raw["params"][param_name] = (param.text or "").strip()
        raw_offers.append(raw)

    # --- Группировка вариантов ---
    products = _group_variants(raw_offers)

    # --- Обогащение category_ids из Tilda API ---
    # Собираем все category_id из YML (включая скрытые) для максимального покрытия
    all_yml_cat_ids = list(set(
        cat.get("id") for cat in shop.findall(".//categories/category")
    ))
    partuids_map = await _fetch_partuids_map(all_yml_cat_ids)
    if partuids_map:
        for product in products:
            pid = product["id"]
            api_cats = partuids_map.get(pid, [])
            if api_cats:
                # Берём категории из API, они полнее
                product["category_ids"] = api_cats
            else:
                # Фоллбэк: одна категория из YML
                product["category_ids"] = [product["category_id"]]
    else:
        # API недоступно — fallback на одну категорию из YML
        for product in products:
            product["category_ids"] = [product["category_id"]]

    # --- Фильтрация скрытых категорий ---
    # Убираем скрытые category_ids, оставляем только видимые
    filtered_products = []
    for product in products:
        visible_cats = [c for c in product["category_ids"] if c not in HIDDEN_CATEGORIES]
        if visible_cats:
            product["category_ids"] = visible_cats
            # Обновляем primary category_id если он был скрытым
            if product["category_id"] in HIDDEN_CATEGORIES:
                product["category_id"] = visible_cats[0]
            filtered_products.append(product)
    
    print(f"📊 После фильтрации: {len(filtered_products)} из {len(products)} товаров "
          f"(убрано {len(products) - len(filtered_products)} без видимых категорий)")

    return {"categories": categories, "products": filtered_products}


def _group_variants(raw_offers: list) -> list:
    """
    Группирует offer-ы с id вида 123v1, 123v2 в один товар с variants[].
    Одиночные товары (без v) — как есть, с пустым variants.
    """
    groups = defaultdict(list)
    order = []  # Сохраняем порядок появления

    for offer in raw_offers:
        oid = offer["id"]
        if "v" in oid:
            base_id = oid[:oid.index("v")]
        else:
            base_id = oid

        if base_id not in groups:
            order.append(base_id)
        groups[base_id].append(offer)

    products = []
    for base_id in order:
        variants_raw = groups[base_id]

        if len(variants_raw) == 1 and "v" not in variants_raw[0]["id"]:
            # Одиночный товар
            p = variants_raw[0]
            # Чистим название (убираем суффикс варианта если есть)
            name = p["name"]
            products.append({
                "id": base_id,
                "name": name,
                "description": clean_description(p["description"] or ""),
                "description_html": p["description"] or "",
                "price": p["price"],
                "old_price": p["old_price"],
                "code": p.get("code") or base_id,
                "category_id": p["category_id"],
                "url": p["url"].split("?")[0] if p["url"] else None,
                "pictures": p["pictures"],
                "count": p["count"],
                "variants": [],
            })
        else:
            # Группа вариантов — берём данные из первого, варианты собираем
            first = variants_raw[0]

            # Базовое название — убираем " - вариант" из конца
            base_name = first["name"]
            if " - " in base_name:
                base_name = base_name[:base_name.rindex(" - ")]

            # Минимальная цена для отображения
            min_price = min(v["price"] for v in variants_raw if v["price"])
            max_price = max(v["price"] for v in variants_raw if v["price"])

            # Собираем варианты
            variants = []
            for v in variants_raw:
                variant_label = v["name"]
                if " - " in variant_label:
                    variant_label = variant_label[variant_label.rindex(" - ") + 3:]

                variants.append({
                    "id": v["id"],
                    "label": variant_label,
                    "price": v["price"],
                    "old_price": v["old_price"],
                    "code": v.get("code") or v["id"],
                    "params": v["params"],
                })

            # Определяем имя параметра варианта
            param_name = ""
            if first["params"]:
                param_name = list(first["params"].keys())[0]

            products.append({
                "id": base_id,
                "name": base_name,
                "description": clean_description(first["description"] or ""),
                "description_html": first["description"] or "",
                "price": min_price,
                "price_max": max_price if max_price != min_price else None,
                "old_price": first["old_price"],
                "code": first.get("code") or base_id,
                "category_id": first["category_id"],
                "url": first["url"].split("?")[0] if first["url"] else None,
                "pictures": first["pictures"],
                "count": max(v["count"] or 0 for v in variants_raw),
                "variant_param": param_name,
                "variants": variants,
            })

    return products
