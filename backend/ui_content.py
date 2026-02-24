"""
Хранилище UI-контента Mini App:
- верхние баннеры
- текст бегущей строки
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path


DATA_DIR = Path("data")
BANNERS_DIR = DATA_DIR / "banners"
UI_CONTENT_FILE = DATA_DIR / "ui_content.json"

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

