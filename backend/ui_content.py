"""
Хранилище UI-контента Mini App:
- верхние баннеры
- текст бегущей строки
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from html import unescape as html_unescape
from pathlib import Path

import httpx

from backend.config import SITE_BANNERS_SOURCE_URL, SITE_BANNERS_TTL_SECONDS

DATA_DIR = Path("data")
BANNERS_DIR = DATA_DIR / "banners"
UI_CONTENT_FILE = DATA_DIR / "ui_content.json"
SITE_BANNERS_CACHE_FILE = DATA_DIR / "site_banners_cache.json"

_LOCK = threading.Lock()

DEFAULT_UI_CONTENT = {
    "ticker_items": [
        "БЕСПЛАТНАЯ ДОСТАВКА ОТ 10 000 ₽ В ПРЕДЕЛАХ КАД",
    ],
    "banners": [],
}


def ensure_ui_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    if not UI_CONTENT_FILE.exists():
        UI_CONTENT_FILE.write_text(
            json.dumps(DEFAULT_UI_CONTENT, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_content(raw: dict) -> dict:
    ticker_items = raw.get("ticker_items", [])
    if not isinstance(ticker_items, list):
        ticker_items = []
    ticker_items = [str(x).strip() for x in ticker_items if str(x).strip()]

    banners = raw.get("banners", [])
    if not isinstance(banners, list):
        banners = []
    normalized_banners = []
    for b in banners:
        if not isinstance(b, dict):
            continue
        normalized_banners.append(
            {
                "id": str(b.get("id", "")).strip() or uuid.uuid4().hex[:8],
                "title": str(b.get("title", "")).strip(),
                "subtitle": str(b.get("subtitle", "")).strip(),
                "target": str(b.get("target", "catalog")).strip() or "catalog",
                "image_url": str(b.get("image_url", "")).strip(),
            }
        )

    return {
        "ticker_items": ticker_items or DEFAULT_UI_CONTENT["ticker_items"],
        "banners": normalized_banners,
    }


def get_ui_content() -> dict:
    ensure_ui_storage()
    with _LOCK:
        try:
            raw = json.loads(UI_CONTENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = DEFAULT_UI_CONTENT
        data = _normalize_content(raw)
        if not data.get("banners"):
            site_banners = _get_site_banners_cached(limit=5)
            if site_banners:
                data["banners"] = site_banners
        UI_CONTENT_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data


def _save_ui_content(data: dict) -> None:
    UI_CONTENT_FILE.write_text(
        json.dumps(_normalize_content(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def set_ticker_items(items: list[str]) -> dict:
    ensure_ui_storage()
    with _LOCK:
        data = get_ui_content()
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        data["ticker_items"] = cleaned or DEFAULT_UI_CONTENT["ticker_items"]
        _save_ui_content(data)
        return data


def set_ticker_text(raw_text: str) -> dict:
    parts = [p.strip() for p in (raw_text or "").split("|")]
    return set_ticker_items(parts)


def add_ticker_item(item: str) -> dict:
    ensure_ui_storage()
    with _LOCK:
        data = get_ui_content()
        text = str(item or "").strip()
        if text:
            data["ticker_items"] = [*data.get("ticker_items", []), text]
        _save_ui_content(data)
        return data


def delete_ticker_item(index: int) -> dict:
    ensure_ui_storage()
    with _LOCK:
        data = get_ui_content()
        items = list(data.get("ticker_items", []))
        if index < 0 or index >= len(items):
            raise IndexError("Ticker item index out of range")
        items.pop(index)
        data["ticker_items"] = items or DEFAULT_UI_CONTENT["ticker_items"]
        _save_ui_content(data)
        return data


def add_banner(
    image_file_path: Path,
    title: str = "",
    subtitle: str = "",
    target: str = "catalog",
) -> dict:
    """
    Регистрирует новый баннер.
    image_file_path — путь к уже сохранённому файлу внутри data/banners.
    """
    ensure_ui_storage()
    with _LOCK:
        data = get_ui_content()
        banner = {
            "id": uuid.uuid4().hex[:10],
            "title": title.strip(),
            "subtitle": subtitle.strip(),
            "target": (target or "catalog").strip(),
            "image_url": f"/media/banners/{image_file_path.name}",
        }
        data["banners"].append(banner)
        _save_ui_content(data)
        return banner


def delete_banner(banner_id: str) -> bool:
    ensure_ui_storage()
    with _LOCK:
        data = get_ui_content()
        banners = data.get("banners", [])
        idx = next((i for i, b in enumerate(banners) if b.get("id") == banner_id), -1)
        if idx == -1:
            return False

        image_url = banners[idx].get("image_url", "")
        file_name = image_url.split("/media/banners/")[-1] if "/media/banners/" in image_url else ""
        if file_name:
            file_path = BANNERS_DIR / file_name
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

        banners.pop(idx)
        data["banners"] = banners
        _save_ui_content(data)
        return True


def list_banners() -> list[dict]:
    return get_ui_content().get("banners", [])


def _get_site_banners_cached(limit: int = 5) -> list[dict]:
    now = int(time.time())
    try:
        if SITE_BANNERS_CACHE_FILE.exists():
            raw = json.loads(SITE_BANNERS_CACHE_FILE.read_text(encoding="utf-8"))
            fetched_at = int(raw.get("fetched_at") or 0)
            banners = raw.get("banners") or []
            if banners and (now - fetched_at) < SITE_BANNERS_TTL_SECONDS:
                return banners[:limit]
    except Exception:
        pass

    banners = _fetch_site_banners(limit=limit)
    if banners:
        try:
            SITE_BANNERS_CACHE_FILE.write_text(
                json.dumps({"fetched_at": now, "banners": banners}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    return banners


def _fetch_site_banners(limit: int = 5) -> list[dict]:
    """
    Пытаемся извлечь hero-изображения из HTML plombirflowers.ru (Tilda JSON-структуры li_img).
    """
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(SITE_BANNERS_SOURCE_URL)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return []

    decoded = html_unescape(html)
    # Пример в HTML: "li_img":"https://static.tildacdn.com/.../F4.jpg"
    img_entries = re.findall(r'"li_img"\s*:\s*"(https://static\.tildacdn\.com[^"]+)"', decoded)
    if not img_entries:
        return []

    preferred = []
    secondary = []
    seen = set()
    for url in img_entries:
        clean = url.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        low = clean.lower()
        if not re.search(r"\.(jpg|jpeg|png|webp)$", low):
            continue
        # В hero чаще фото, а не сервисные иконки.
        if re.search(r"/(f\d+|frame[_-]?\d+|\d+)\.(jpg|jpeg|webp)$", low):
            preferred.append(clean)
        else:
            secondary.append(clean)

    selected = (preferred + secondary)[:limit]
    return [
        {
            "id": f"site-{i+1}",
            "title": "",
            "subtitle": "",
            "target": "catalog",
            "image_url": url,
        }
        for i, url in enumerate(selected)
    ]

