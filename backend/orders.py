"""
Хранение и управление заказами — SQLite.
"""
import sqlite3
import json
import datetime
import os
from typing import Optional, List

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "orders.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Создаём таблицу заказов если не существует."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id TEXT,
            telegram_username TEXT,
            customer_name TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            delivery_address TEXT,
            delivery_date TEXT,
            delivery_time TEXT,
            comment TEXT,
            card_text TEXT,
            items TEXT NOT NULL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_order(order_data: dict) -> dict:
    """Создаёт заказ, возвращает его с id."""
    conn = _get_conn()
    now = datetime.datetime.now().isoformat()

    cursor = conn.execute("""
        INSERT INTO orders (
            telegram_user_id, telegram_username,
            customer_name, customer_phone,
            delivery_address, delivery_date, delivery_time,
            comment, card_text,
            items, total, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
    """, (
        order_data.get("telegram_user_id", ""),
        order_data.get("telegram_username", ""),
        order_data["customer_name"],
        order_data["customer_phone"],
        order_data.get("delivery_address", ""),
        order_data.get("delivery_date", ""),
        order_data.get("delivery_time", ""),
        order_data.get("comment", ""),
        order_data.get("card_text", ""),
        json.dumps(order_data["items"], ensure_ascii=False),
        order_data["total"],
        now,
    ))
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()

    return {
        "id": order_id,
        "status": "new",
        "created_at": now,
        **order_data,
    }


def get_order(order_id: int) -> Optional[dict]:
    """Получает заказ по id."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def get_orders_by_user(telegram_user_id: str) -> list:
    """Получает заказы пользователя."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM orders WHERE telegram_user_id = ? ORDER BY id DESC",
        (telegram_user_id,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["items"] = json.loads(d["items"])
    return d
