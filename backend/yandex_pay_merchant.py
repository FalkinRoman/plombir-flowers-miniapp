"""
Прямой приём оплаты через Yandex Pay Merchant API (/v1/orders, вебхук /v1/webhook).
Документация: https://pay.yandex.ru/docs/ru/custom/backend/yandex-pay-api/
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import jwt
from jwt import PyJWKClient

from backend.config import (
    YANDEX_PAY_API_BASE,
    YANDEX_PAY_CHECKOUT_ENABLED,
    YANDEX_PAY_JWKS_URL,
    YANDEX_PAY_MERCHANT_API_KEY,
    YANDEX_PAY_MERCHANT_ID,
    YANDEX_PAY_RETURN_URL,
)

log = logging.getLogger("plombir.yandex_pay")

_jwks_client: Optional[PyJWKClient] = None


class YandexPayConfigError(RuntimeError):
    pass


def is_yandex_checkout_ready() -> bool:
    if not YANDEX_PAY_CHECKOUT_ENABLED:
        return False
    return bool(YANDEX_PAY_MERCHANT_API_KEY and YANDEX_PAY_MERCHANT_ID and YANDEX_PAY_RETURN_URL)


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(YANDEX_PAY_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_webhook_jwt(raw_body: bytes) -> dict[str, Any]:
    token = raw_body.decode("utf-8").strip()
    if not token:
        raise ValueError("empty webhook body")
    signing_key = _jwks().get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256"],
        options={"verify_aud": False},
    )
    if not isinstance(payload, dict):
        raise ValueError("invalid jwt payload")
    mid = str(payload.get("merchantId") or "")
    if YANDEX_PAY_MERCHANT_ID and mid and mid != YANDEX_PAY_MERCHANT_ID:
        raise ValueError("merchantId mismatch")
    return payload


def _build_return_urls(order_id: int) -> dict[str, str]:
    base = (YANDEX_PAY_RETURN_URL or "").strip()
    if not base:
        return {}
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["order_id"] = str(order_id)

    def _with(extra: dict[str, str]) -> str:
        q = {**query, **extra}
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

    return {
        "onSuccess": _with({"pay": "ok"}),
        "onAbort": _with({"pay": "abort"}),
        "onError": _with({"pay": "error"}),
    }


def _digits_phone(phone: str) -> str:
    d = re.sub(r"\D+", "", phone or "")
    if d.startswith("8") and len(d) >= 11:
        d = "7" + d[1:]
    if d.startswith("9") and len(d) == 10:
        d = "7" + d
    return d


def _cart_from_items(
    items: list[dict[str, Any]],
    pay_amount: float,
    fiscal_tax: Optional[int],
) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for i, it in enumerate(items):
        pid = str(it.get("product_id") or f"item-{i}")
        vid = it.get("variant_id")
        product_id = f"{pid}:{vid}" if vid else pid
        title = str(it.get("name") or "Товар")
        vl = it.get("variant_label")
        if vl:
            title = f"{title} ({vl})"
        qty = int(it.get("quantity") or 1)
        price = float(it.get("price") or 0)
        line_total = round(price * qty, 2)
        entry: dict[str, Any] = {
            "productId": product_id[:2048],
            "title": title[:500],
            "quantity": {"count": str(qty)},
            "total": f"{line_total:.2f}",
            "unitPrice": f"{price:.2f}",
        }
        if fiscal_tax is not None:
            entry["receipt"] = {"tax": fiscal_tax}
        lines.append(entry)

    items_sum = round(sum(float(x["total"]) for x in lines), 2)
    pay_amount = round(max(pay_amount, 1.0), 2)
    external = round(max(0.0, items_sum - pay_amount), 2)
    cart: dict[str, Any] = {
        "items": lines,
        "total": {"amount": f"{pay_amount:.2f}"},
    }
    if external > 0:
        cart["total"]["externalAmount"] = f"{external:.2f}"
    return cart


async def create_checkout_order(
    *,
    order_id: int,
    payment_method: str,
    items: list[dict[str, Any]],
    total: float,
    customer_phone: str,
    fiscal_tax: Optional[int] = None,
) -> dict[str, Any]:
    """
    POST /v1/orders → редирект на data.paymentUrl.
    payment_method: card | split
    """
    if not is_yandex_checkout_ready():
        raise YandexPayConfigError("Yandex Pay Merchant API не настроен (ключ, merchant id, return URL)")

    if payment_method == "split":
        methods = ["CARD", "SPLIT"]
        preferred = "SPLIT"
    elif payment_method == "card":
        methods = ["CARD"]
        preferred = "FULLPAYMENT"
    else:
        raise YandexPayConfigError(f"Неизвестный способ: {payment_method}")

    redirect_urls = _build_return_urls(order_id)
    if not redirect_urls.get("onSuccess"):
        raise YandexPayConfigError("YANDEX_PAY_RETURN_URL не задан")

    phone = _digits_phone(customer_phone)
    if fiscal_tax is not None and not phone:
        fiscal_tax = None

    cart = _cart_from_items(items, float(total), fiscal_tax)
    body: dict[str, Any] = {
        "orderId": str(order_id),
        "currencyCode": "RUB",
        "availablePaymentMethods": methods,
        "preferredPaymentMethod": preferred,
        "cart": cart,
        "redirectUrls": redirect_urls,
        "metadata": json.dumps({"order_id": order_id, "flow": payment_method}, ensure_ascii=False),
    }
    if phone:
        body["risk"] = {
            "billingPhone": phone,
            "shippingPhone": phone,
        }
    if fiscal_tax is not None and phone:
        body["fiscalContact"] = phone

    url = f"{YANDEX_PAY_API_BASE.rstrip('/')}/v1/orders"
    headers = {
        "Authorization": f"Api-Key {YANDEX_PAY_MERCHANT_API_KEY}",
        "Content-Type": "application/json",
        "X-Request-Id": str(uuid.uuid4()),
        "X-Request-Timeout": "10000",
        "X-Request-Attempt": "0",
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(url, json=body, headers=headers)
    text = (resp.text or "")[:1200]
    try:
        data = resp.json()
    except Exception:
        data = None
    if resp.status_code >= 400:
        detail = text
        if isinstance(data, dict):
            detail = str(data.get("reason") or data.get("message") or data.get("status") or detail)[:800]
        raise RuntimeError(f"Yandex Pay API HTTP {resp.status_code}: {detail}")
    if not isinstance(data, dict):
        raise RuntimeError("Yandex Pay API: не JSON в ответе")
    code_ok = data.get("code") in (200, "200")
    if data.get("status") != "success" or not code_ok:
        detail = str(data.get("reason") or data)[:800]
        raise RuntimeError(f"Yandex Pay API: {detail}")
    inner = data.get("data") or {}
    payment_url = inner.get("paymentUrl")
    if not payment_url:
        raise RuntimeError("Yandex Pay API: нет data.paymentUrl")
    return {
        "payment_id": str(order_id),
        "confirmation_url": payment_url,
        "status": "pending",
        "raw": data,
    }
