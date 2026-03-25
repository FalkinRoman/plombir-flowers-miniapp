"""
Интеграция с ЮKassa.
Работает в двух режимах:
1) real mode - при наличии ключей и YOOKASSA_ENABLED=1
2) disabled mode - возвращает RuntimeError с понятным текстом
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from backend.config import (
    SPLIT_PAYMENT_METHOD_DATA_TYPE,
    YOOKASSA_ENABLED,
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)


class PaymentConfigError(RuntimeError):
    pass


def is_yookassa_ready() -> bool:
    if not YOOKASSA_ENABLED:
        return False
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY and YOOKASSA_RETURN_URL)


def _headers() -> dict[str, str]:
    return {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def _build_return_url(order_id: int) -> str:
    """
    Добавляем order_id в return_url, чтобы фронт после возврата мог показать фактический статус оплаты.
    """
    base = (YOOKASSA_RETURN_URL or "").strip()
    if not base:
        return base
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["order_id"] = str(order_id)
    new_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


async def create_payment(
    *,
    order_id: int,
    amount_rub: float,
    description: str,
    customer_phone: str = "",
    payment_method: str = "card",
) -> dict[str, Any]:
    """
    Создает платеж в ЮKassa и возвращает raw response.
    payment_method:
      - card -> bank_card (страница ЮKassa)
      - split -> yandex_pay по умолчанию (редирект на Яндекс Пэй; Сплит — если подключён в кабинете ЮKassa/Яндекс)
    """
    if not is_yookassa_ready():
        raise PaymentConfigError("ЮKassa не настроена: включите флаг и заполните ключи")

    method_data: Optional[dict[str, str]] = None
    if payment_method == "card":
        method_data = {"type": "bank_card"}
    elif payment_method == "split":
        sm = SPLIT_PAYMENT_METHOD_DATA_TYPE if SPLIT_PAYMENT_METHOD_DATA_TYPE in {"yandex_pay", "bank_card"} else "yandex_pay"
        method_data = {"type": sm}

    payload = {
        "amount": {
            "value": f"{max(amount_rub, 1):.2f}",
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": _build_return_url(order_id),
        },
        "description": description,
        "metadata": {
            "order_id": str(order_id),
            "payment_flow": payment_method,
        },
    }
    if method_data:
        payload["payment_method_data"] = method_data
    if customer_phone:
        payload["receipt"] = {
            "customer": {"phone": customer_phone},
            "items": [
                {
                    "description": description[:128] or f"Заказ #{order_id}",
                    "quantity": "1.00",
                    "amount": {"value": f"{max(amount_rub, 1):.2f}", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }
            ],
        }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()
