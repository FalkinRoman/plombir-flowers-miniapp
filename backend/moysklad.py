"""
Интеграция с МойСклад (этап 3).
Создаём customerorder после успешной оплаты.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote
import datetime as dt

import httpx

from backend.config import MOYSKLAD_ENABLED, MOYSKLAD_ORG_ID, MOYSKLAD_TOKEN, MOYSKLAD_STORE_ID
from backend.config import MOYSKLAD_GROUP_ID, MOYSKLAD_SALES_CHANNEL_ID, MOYSKLAD_DEFAULT_AGENT_ID

MS_API_BASE = "https://api.moysklad.ru/api/remap/1.2"
MS_CURRENCY_HREF = f"{MS_API_BASE}/entity/currency/22a8698c-9708-11ec-0a80-099a001a3a8a"

MS_DELIVERY_MAP = {
    "Узнать адрес у получателя*": f"{MS_API_BASE}/entity/customentity/8d12edfc-b918-11ed-0a80-0d200033652e/4c0f6594-4be7-11ee-0a80-07da0010d829",
    "Самовывоз с пр. Добролюбова 27": f"{MS_API_BASE}/entity/customentity/8d12edfc-b918-11ed-0a80-0d200033652e/9acf8deb-b984-11ed-0a80-085e00093fda",
    "Самовывоз с ул. Кирочная 8Б": f"{MS_API_BASE}/entity/customentity/8d12edfc-b918-11ed-0a80-0d200033652e/f886c975-2404-11ef-0a80-11330015e290",
    "Курьер": f"{MS_API_BASE}/entity/customentity/8d12edfc-b918-11ed-0a80-0d200033652e/e5c471be-b921-11ed-0a80-1181003bcb9c",
}
MS_CONTACT_MAP = {
    "Связываться не нужно (только в случае необходимости пересогласовать состав заказа)": f"{MS_API_BASE}/entity/customentity/04c37444-4be6-11ee-0a80-0dcf0010471c/1d83659d-4be6-11ee-0a80-107f0010f7e6",
    "WhatsApp": f"{MS_API_BASE}/entity/customentity/04c37444-4be6-11ee-0a80-0dcf0010471c/29381840-4be6-11ee-0a80-07da00109d2b",
    "Telegram": f"{MS_API_BASE}/entity/customentity/04c37444-4be6-11ee-0a80-0dcf0010471c/35ce67fb-4be6-11ee-0a80-0e650010dbd2",
}
MS_ATTRS = {
    "delivery": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0c725-b919-11ed-0a80-032600302976",
    "address": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0ca3a-b919-11ed-0a80-032600302978",
    "date": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0c359-b919-11ed-0a80-032600302975",
    "time": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0c916-b919-11ed-0a80-032600302977",
    "card_text": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0cc5c-b919-11ed-0a80-03260030297a",
    "recipient_name": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/5cc0cb5c-b919-11ed-0a80-032600302979",
    "recipient_phone": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/8824fa2b-4be6-11ee-0a80-0b160010fc12",
    "courier_comment": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/8dbc86a5-f4f1-11ef-0a80-1045000a6e8d",
    "telegram_nickname": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/44acd8a8-fd16-11f0-0a80-02950011780f",
    "contact_method": f"{MS_API_BASE}/entity/customerorder/metadata/attributes/0ab1e2e0-4be6-11ee-0a80-01e40010cb5a",
}


def is_moysklad_ready() -> bool:
    return bool(MOYSKLAD_ENABLED and MOYSKLAD_TOKEN and MOYSKLAD_ORG_ID)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
    }


async def create_customerorder(order: dict) -> Optional[str]:
    """
    Пытается создать customerorder и возвращает его id.
    Если интеграция выключена — None.
    """
    if not is_moysklad_ready():
        return None

    description_lines = [
        f"Mini App заказ #{order.get('id')}",
        f"Клиент: {order.get('customer_name') or '-'}",
        f"Телефон: {order.get('customer_phone') or '-'}",
        f"Адрес: {order.get('delivery_address') or '-'}",
        f"Дата/время: {(order.get('delivery_date') or '-')} {(order.get('delivery_time') or '')}".strip(),
        f"Получатель: {order.get('recipient_name') or '-'}",
        f"Телефон получателя: {order.get('recipient_phone') or '-'}",
        f"Открытка: {order.get('card_text') or '-'}",
        "Товары:",
    ]
    requires_manual_replace = []
    for item in order.get("items") or []:
        line = f"- {item.get('name')} x{item.get('quantity')} ({item.get('price')} RUB)"
        if item.get("variant_label"):
            line += f", {item.get('variant_label')}"
        if item.get("product_code"):
            line += f", code={item.get('product_code')}"
        description_lines.append(line)
        if item.get("variant_id"):
            requires_manual_replace.append(item.get("product_code") or item.get("product_id"))
    if order.get("comment"):
        description_lines.append(f"Комментарий: {order['comment']}")
    if requires_manual_replace:
        description_lines.append(
            "Групповые позиции (ручная замена менеджером): " + ", ".join(str(x) for x in requires_manual_replace)
        )

    payload: dict[str, Any] = {
        "name": f"TG-{order.get('id')}",
        "description": "\n".join(description_lines)[:4096],
        "organization": {
            "meta": {
                "href": f"{MS_API_BASE}/entity/organization/{MOYSKLAD_ORG_ID}",
                "type": "organization",
                "mediaType": "application/json",
            }
        },
        "attributes": _build_attributes(order),
    }
    if MOYSKLAD_DEFAULT_AGENT_ID:
        payload["agent"] = {
            "meta": {
                "href": f"{MS_API_BASE}/entity/counterparty/{MOYSKLAD_DEFAULT_AGENT_ID}",
                "type": "counterparty",
                "mediaType": "application/json",
            }
        }
    if MOYSKLAD_STORE_ID:
        payload["store"] = {
            "meta": {
                "href": f"{MS_API_BASE}/entity/store/{MOYSKLAD_STORE_ID}",
                "type": "store",
                "mediaType": "application/json",
            }
        }
    if MOYSKLAD_GROUP_ID:
        payload["group"] = {
            "meta": {
                "href": f"{MS_API_BASE}/entity/group/{MOYSKLAD_GROUP_ID}",
                "type": "group",
                "mediaType": "application/json",
            }
        }
    if MOYSKLAD_SALES_CHANNEL_ID:
        payload["salesChannel"] = {
            "meta": {
                "href": f"{MS_API_BASE}/entity/saleschannel/{MOYSKLAD_SALES_CHANNEL_ID}",
                "type": "saleschannel",
                "mediaType": "application/json",
            }
        }

    positions = await _build_positions(order)
    if positions:
        payload["positions"] = positions

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{MS_API_BASE}/entity/customerorder",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("id")


async def _build_positions(order: dict) -> list[dict[str, Any]]:
    """
    Логика как на сайте:
    - одиночные товары -> ищем в МС по коду и добавляем позицию;
    - групповые (variant_id) -> позицию не заполняем автоматически, только маркер в description.
    """
    items = order.get("items") or []
    if not items:
        return []
    positions: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for item in items:
            code = str(item.get("product_code") or item.get("product_id") or "").strip()
            if not code:
                continue
            assortment_meta = await _get_or_create_product_meta(
                client,
                code=code,
                name=str(item.get("name") or code),
                price=float(item.get("price") or 0),
            )
            if not assortment_meta:
                continue
            qty = float(item.get("quantity") or 1)
            price = float(item.get("price") or 0)
            if item.get("variant_id"):
                # Групповой товар: позиция-пустышка с кодом, менеджер меняет вручную.
                qty = 1.0
            positions.append({
                "quantity": qty,
                "price": int(round(max(price, 0) * 100)),
                "assortment": {"meta": assortment_meta},
            })
    return positions


async def _find_product_meta_by_code(client: httpx.AsyncClient, code: str) -> Optional[dict[str, Any]]:
    # В МС фильтр по code:
    # /entity/product?filter=code=<значение>
    encoded = quote(code, safe="")
    url = f"{MS_API_BASE}/entity/product?filter=code={encoded}&limit=1"
    resp = await client.get(url, headers=_headers())
    if resp.status_code >= 400:
        return None
    rows = (resp.json() or {}).get("rows") or []
    if not rows:
        return None
    meta = (rows[0] or {}).get("meta")
    return meta if isinstance(meta, dict) else None


async def _get_or_create_product_meta(
    client: httpx.AsyncClient,
    *,
    code: str,
    name: str,
    price: float,
) -> Optional[dict[str, Any]]:
    meta = await _find_product_meta_by_code(client, code)
    if meta:
        return meta
    payload = {
        "name": name[:255],
        "code": code,
        "externalCode": code,
        "salePrices": [
            {
                "value": int(round(max(price, 0) * 100)),
                "currency": {"meta": {"href": MS_CURRENCY_HREF, "type": "currency"}},
            }
        ],
    }
    resp = await client.post(f"{MS_API_BASE}/entity/product", headers=_headers(), json=payload)
    if resp.status_code >= 400:
        return None
    data = resp.json() or {}
    meta = data.get("meta")
    return meta if isinstance(meta, dict) else None


def _build_attributes(order: dict) -> list[dict[str, Any]]:
    attrs: list[dict[str, Any]] = []

    delivery_type = str(order.get("delivery_type") or "").strip()
    delivery_href = MS_DELIVERY_MAP.get(delivery_type)
    if delivery_href:
        attrs.append({
            "meta": {"href": MS_ATTRS["delivery"], "type": "attributemetadata"},
            "value": {"meta": {"href": delivery_href, "type": "customentity"}},
        })

    address = str(order.get("delivery_address") or "").strip()
    if address:
        attrs.append({
            "meta": {"href": MS_ATTRS["address"], "type": "attributemetadata"},
            "type": "text",
            "value": address,
        })

    delivery_date = str(order.get("delivery_date") or "").strip()
    if delivery_date:
        try:
            d = dt.datetime.strptime(delivery_date, "%Y-%m-%d")
            value = d.strftime("%Y-%m-%d 00:00:00")
            attrs.append({
                "meta": {"href": MS_ATTRS["date"], "type": "attributemetadata"},
                "type": "time",
                "value": value,
            })
        except ValueError:
            pass

    for key, attr_key, value_type in [
        ("delivery_time", "time", "string"),
        ("card_text", "card_text", "string"),
        ("recipient_name", "recipient_name", "string"),
        ("recipient_phone", "recipient_phone", "string"),
        ("courier_comment", "courier_comment", "string"),
        ("telegram_nickname", "telegram_nickname", "string"),
    ]:
        value = str(order.get(key) or "").strip()
        if value:
            attrs.append({
                "meta": {"href": MS_ATTRS[attr_key], "type": "attributemetadata"},
                "type": value_type,
                "value": value,
            })

    contact_method = str(order.get("contact_method") or "").strip()
    contact_href = MS_CONTACT_MAP.get(contact_method)
    if contact_href:
        attrs.append({
            "meta": {"href": MS_ATTRS["contact_method"], "type": "attributemetadata"},
            "value": {"meta": {"href": contact_href, "type": "customentity"}},
        })

    return attrs
