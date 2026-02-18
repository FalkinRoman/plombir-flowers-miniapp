"""
Парсер YML-фида Тильды.
Загружает, парсит, группирует варианты, чистит описания.
"""
import re
import httpx
from lxml import etree
from typing import Optional
from collections import defaultdict
from backend.config import YML_FEED_URL, HIDDEN_CATEGORIES, BOILERPLATE_TEXTS


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


async def fetch_and_parse() -> dict:
    """
    Загружает YML-фид, парсит, группирует варианты.
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

    # --- Товары (сырые) ---
    raw_offers = []
    for offer in shop.findall(".//offers/offer"):
        cat_id = _text(offer, "categoryId")
        # Пропускаем товары из скрытых категорий
        if cat_id in HIDDEN_CATEGORIES:
            continue

        raw = {
            "id": offer.get("id"),
            "name": _text(offer, "name"),
            "description": _text(offer, "description"),
            "price": _float(offer, "price"),
            "old_price": _float(offer, "oldprice"),
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

    return {"categories": categories, "products": products}


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
                "category_id": first["category_id"],
                "url": first["url"].split("?")[0] if first["url"] else None,
                "pictures": first["pictures"],
                "count": max(v["count"] or 0 for v in variants_raw),
                "variant_param": param_name,
                "variants": variants,
            })

    return products
