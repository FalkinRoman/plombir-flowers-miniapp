"""
Интеграция с МойСклад (этап 3).
Создаём customerorder после успешной оплаты.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from backend.config import MOYSKLAD_ENABLED, MOYSKLAD_ORG_ID, MOYSKLAD_TOKEN, MOYSKLAD_STORE_ID

MS_API_BASE = "https://api.moysklad.ru/api/remap/1.2"


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
        "Товары:",
    ]
    for item in order.get("items") or []:
        line = f"- {item.get('name')} x{item.get('quantity')} ({item.get('price')} RUB)"
        if item.get("variant_label"):
            line += f", {item.get('variant_label')}"
        description_lines.append(line)
    if order.get("comment"):
        description_lines.append(f"Комментарий: {order['comment']}")

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
        "attributes": [],
    }
    if MOYSKLAD_STORE_ID:
        payload["store"] = {
            "meta": {
                "href": f"{MS_API_BASE}/entity/store/{MOYSKLAD_STORE_ID}",
                "type": "store",
                "mediaType": "application/json",
            }
        }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{MS_API_BASE}/entity/customerorder",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("id")
