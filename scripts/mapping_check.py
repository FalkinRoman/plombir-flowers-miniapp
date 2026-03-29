#!/usr/bin/env python3
"""
Сверка YML (Tilda) ↔ МойСклад: повторяет порядок поиска из backend/moysklad.py::_resolve_assortment_meta,
но без создания товаров — только «нашли / не нашли».

Переменные окружения:
  MOYSKLAD_TOKEN — токен API (как в проде) или MS_TOKEN
  YML_URL — URL фида (по умолчанию встроенный)

Опционально:
  MS_BASE — https://api.moysklad.ru/api/remap/1.2
  OUT_DIR — каталог для CSV (по умолчанию текущий)

Пример:
  export MOYSKLAD_TOKEN='...'
  export YML_URL='https://plombirflowers.ru/tstore/yml/....yml'
  python3 scripts/mapping_check.py
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import quote

import requests

MS_BASE = os.getenv("MS_BASE", "https://api.moysklad.ru/api/remap/1.2")
YML_URL = os.getenv(
    "YML_URL",
    "https://plombirflowers.ru/tstore/yml/f71b0604abcdbc4a00be062b0784460e.yml",
)
OUT_DIR = os.getenv("OUT_DIR", ".")
TIMEOUT = 40
REQUEST_PAUSE = float(os.getenv("REQUEST_PAUSE", "0.03"))


def _headers() -> dict[str, str]:
    token = (os.getenv("MOYSKLAD_TOKEN") or os.getenv("MS_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "Задай MOYSKLAD_TOKEN (или MS_TOKEN) — тот же токен, что в .env бэкенда."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json;charset=utf-8",
        "Accept-Encoding": "gzip",
    }


def _norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _expand_assortment_lookup_candidates(*parts: str) -> list[str]:
    """Копия логики backend/moysklad.py — кандидаты для code / externalCode."""
    seen: list[str] = []
    for raw in parts:
        s = (raw or "").strip()
        if not s:
            continue
        if s not in seen:
            seen.append(s)
        if "v" in s:
            i = s.rindex("v")
            if i > 0 and s[i + 1 :].isdigit():
                base = s[:i]
                if base and base not in seen:
                    seen.append(base)
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 6 and digits not in seen:
            seen.append(digits)
    return seen


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_headers())
    return s


def _get_rows_json(sess: requests.Session, url: str) -> Optional[dict[str, Any]]:
    time.sleep(REQUEST_PAUSE)
    r = sess.get(url, timeout=TIMEOUT)
    if r.status_code >= 400:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _first_meta_from_filter(sess: requests.Session, entity: str, field: str, value: str) -> Optional[dict[str, Any]]:
    encoded = quote(value, safe="")
    url = f"{MS_BASE}/entity/{entity}?filter={field}={encoded}&limit=1"
    data = _get_rows_json(sess, url)
    if not data:
        return None
    rows = data.get("rows") or []
    if not rows:
        return None
    meta = (rows[0] or {}).get("meta")
    return meta if isinstance(meta, dict) else None


def resolve_assortment_meta_no_create(
    sess: requests.Session,
    *,
    code: str,
    product_id: str,
    name: str,
) -> tuple[Optional[dict[str, Any]], str]:
    """
    Как _resolve_assortment_meta, но без создания товара.
    Возвращает (meta, reason) или (None, 'not_found').
    """
    for candidate in _expand_assortment_lookup_candidates(code, product_id):
        for step in (
            ("assortment", "code", "assortment_code"),
            ("assortment", "externalCode", "assortment_externalCode"),
            ("product", "code", "product_code"),
            ("product", "externalCode", "product_externalCode"),
        ):
            entity, field, _ = step
            meta = _first_meta_from_filter(sess, entity, field, candidate)
            if meta:
                return meta, f"{step[2]}:{candidate}"

    if name:
        encoded = quote(name.strip(), safe="")
        url = f"{MS_BASE}/entity/product?filter=name={encoded}&limit=1"
        data = _get_rows_json(sess, url)
        if data:
            rows = data.get("rows") or []
            if rows:
                meta = (rows[0] or {}).get("meta")
                if isinstance(meta, dict):
                    return meta, f"product_name:{name[:80]}"

    return None, "not_found"


def parse_yml(url: str) -> list[dict[str, str]]:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    offers: list[dict[str, str]] = []
    for offer in root.findall(".//offer"):
        offer_id = _norm(offer.attrib.get("id"))
        name = _norm(offer.findtext("name"))
        vendor_code = _norm(offer.findtext("vendorCode"))
        article = _norm(offer.findtext("article"))
        barcode = _norm(offer.findtext("barcode"))

        params: dict[str, str] = {}
        for p in offer.findall("param"):
            pn = _norm(p.attrib.get("name")).lower().replace("ё", "е")
            pv = _norm(p.text)
            if pn:
                params[pn] = pv

        article_param = (
            params.get("артикул")
            or params.get("article")
            or params.get("vendorcode")
            or params.get("код товара")
            or ""
        )

        # Как в мини-аппе часто кладут product_code: приоритет вендора/артикула
        lookup_code = vendor_code or article or article_param or offer_id

        offers.append(
            {
                "offer_id": offer_id,
                "offer_name": name,
                "vendor_code": vendor_code,
                "article": article,
                "article_param": article_param,
                "barcode": barcode,
                "lookup_code": lookup_code,
            }
        )
    return offers


def write_csv(path: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"[1/3] YML: {YML_URL}")
    offers = parse_yml(YML_URL)
    print(f"      офферов: {len(offers)}")

    print("[2/3] Запросы к МойСклад (это может занять 1–10 мин при большом каталоге)")
    sess = _session()
    report: list[dict[str, Any]] = []
    name_only: list[dict[str, Any]] = []
    not_found: list[dict[str, Any]] = []

    for i, off in enumerate(offers):
        offer_id = off["offer_id"]
        name = off["offer_name"]
        lookup_code = off["lookup_code"]
        meta, reason = resolve_assortment_meta_no_create(
            sess,
            code=lookup_code,
            product_id=offer_id,
            name=name,
        )
        href = (meta or {}).get("href", "") if meta else ""
        mtype = (meta or {}).get("type", "") if meta else ""
        mid = ""
        if href and "/entity/" in href:
            mid = href.rstrip("/").split("/")[-1]

        row = {
            "offer_id": offer_id,
            "offer_name": name,
            "lookup_code": lookup_code,
            "vendor_code": off["vendor_code"],
            "article": off["article"],
            "resolution": reason,
            "ms_href": href,
            "ms_type": mtype,
            "ms_id": mid,
        }
        report.append(row)

        if meta is None:
            not_found.append(row)
        elif reason.startswith("product_name:"):
            name_only.append({**row, "note": "matched_by_name_only"})

        if (i + 1) % 100 == 0:
            print(f"      обработано {i + 1}/{len(offers)}")

    print("[3/3] CSV")
    base_fields = [
        "offer_id",
        "offer_name",
        "lookup_code",
        "vendor_code",
        "article",
        "resolution",
        "ms_href",
        "ms_type",
        "ms_id",
    ]
    write_csv(os.path.join(OUT_DIR, "mapping_report.csv"), report, base_fields)
    write_csv(
        os.path.join(OUT_DIR, "not_found.csv"),
        not_found,
        base_fields,
    )
    write_csv(
        os.path.join(OUT_DIR, "matched_by_name_only.csv"),
        name_only,
        base_fields + ["note"],
    )

    matched = len(offers) - len(not_found)
    print(
        f"Готово: matched={matched}, not_found={len(not_found)}, "
        f"name_only={len(name_only)}"
    )
    print(f"  {OUT_DIR}/mapping_report.csv")
    print(f"  {OUT_DIR}/not_found.csv")
    print(f"  {OUT_DIR}/matched_by_name_only.csv")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
