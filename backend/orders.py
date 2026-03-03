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
            delivery_type TEXT,
            contact_method TEXT,
            recipient_name TEXT,
            recipient_phone TEXT,
            courier_comment TEXT,
            telegram_nickname TEXT,
            comment TEXT,
            card_text TEXT,
            items TEXT NOT NULL,
            subtotal REAL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'Создан',
            payment_method TEXT DEFAULT 'manual',
            payment_status TEXT DEFAULT 'not_required',
            payment_id TEXT,
            payment_url TEXT,
            split_months INTEGER,
            split_monthly_payment REAL,
            loyalty_points_used REAL DEFAULT 0,
            inventory_state TEXT DEFAULT 'none',
            moysklad_order_id TEXT,
            moysklad_sync_error TEXT,
            created_at TEXT NOT NULL
        )
    """)
    _migrate_orders_schema(conn)
    conn.commit()
    conn.close()


def _migrate_orders_schema(conn: sqlite3.Connection):
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(orders)").fetchall()
    }
    migrations = [
        ("subtotal", "ALTER TABLE orders ADD COLUMN subtotal REAL"),
        ("payment_method", "ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'manual'"),
        ("payment_status", "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'not_required'"),
        ("payment_id", "ALTER TABLE orders ADD COLUMN payment_id TEXT"),
        ("payment_url", "ALTER TABLE orders ADD COLUMN payment_url TEXT"),
        ("split_months", "ALTER TABLE orders ADD COLUMN split_months INTEGER"),
        ("split_monthly_payment", "ALTER TABLE orders ADD COLUMN split_monthly_payment REAL"),
        ("loyalty_points_used", "ALTER TABLE orders ADD COLUMN loyalty_points_used REAL DEFAULT 0"),
        ("inventory_state", "ALTER TABLE orders ADD COLUMN inventory_state TEXT DEFAULT 'none'"),
        ("moysklad_order_id", "ALTER TABLE orders ADD COLUMN moysklad_order_id TEXT"),
        ("moysklad_sync_error", "ALTER TABLE orders ADD COLUMN moysklad_sync_error TEXT"),
        ("delivery_type", "ALTER TABLE orders ADD COLUMN delivery_type TEXT"),
        ("contact_method", "ALTER TABLE orders ADD COLUMN contact_method TEXT"),
        ("recipient_name", "ALTER TABLE orders ADD COLUMN recipient_name TEXT"),
        ("recipient_phone", "ALTER TABLE orders ADD COLUMN recipient_phone TEXT"),
        ("courier_comment", "ALTER TABLE orders ADD COLUMN courier_comment TEXT"),
        ("telegram_nickname", "ALTER TABLE orders ADD COLUMN telegram_nickname TEXT"),
    ]
    for column_name, stmt in migrations:
        if column_name not in existing:
            conn.execute(stmt)


def create_order(order_data: dict) -> dict:
    """Создаёт заказ, возвращает его с id."""
    conn = _get_conn()
    now = datetime.datetime.now().isoformat()

    cursor = conn.execute("""
        INSERT INTO orders (
            telegram_user_id, telegram_username,
            customer_name, customer_phone,
            delivery_address, delivery_date, delivery_time,
            delivery_type, contact_method, recipient_name, recipient_phone, courier_comment, telegram_nickname,
            comment, card_text,
            items, subtotal, total, status,
            payment_method, payment_status, payment_id, payment_url,
            split_months, split_monthly_payment, loyalty_points_used,
            inventory_state, moysklad_order_id, moysklad_sync_error,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_data.get("telegram_user_id", ""),
        order_data.get("telegram_username", ""),
        order_data["customer_name"],
        order_data["customer_phone"],
        order_data.get("delivery_address", ""),
        order_data.get("delivery_date", ""),
        order_data.get("delivery_time", ""),
        order_data.get("delivery_type", ""),
        order_data.get("contact_method", ""),
        order_data.get("recipient_name", ""),
        order_data.get("recipient_phone", ""),
        order_data.get("courier_comment", ""),
        order_data.get("telegram_nickname", ""),
        order_data.get("comment", ""),
        order_data.get("card_text", ""),
        json.dumps(order_data["items"], ensure_ascii=False),
        order_data.get("subtotal", order_data["total"]),
        order_data["total"],
        order_data.get("status", "Создан"),
        order_data.get("payment_method", "manual"),
        order_data.get("payment_status", "not_required"),
        order_data.get("payment_id"),
        order_data.get("payment_url"),
        order_data.get("split_months"),
        order_data.get("split_monthly_payment"),
        order_data.get("loyalty_points_used", 0),
        order_data.get("inventory_state", "none"),
        order_data.get("moysklad_order_id"),
        order_data.get("moysklad_sync_error"),
        now,
    ))
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()

    return {
        "id": order_id,
        "status": order_data.get("status", "Создан"),
        "created_at": now,
        **order_data,
    }


def update_order_payment(
    order_id: int,
    *,
    payment_status: Optional[str] = None,
    payment_id: Optional[str] = None,
    payment_url: Optional[str] = None,
    status: Optional[str] = None,
    inventory_state: Optional[str] = None,
):
    conn = _get_conn()
    sets = []
    values = []
    if payment_status is not None:
        sets.append("payment_status = ?")
        values.append(payment_status)
    if payment_id is not None:
        sets.append("payment_id = ?")
        values.append(payment_id)
    if payment_url is not None:
        sets.append("payment_url = ?")
        values.append(payment_url)
    if status is not None:
        sets.append("status = ?")
        values.append(status)
    if inventory_state is not None:
        sets.append("inventory_state = ?")
        values.append(inventory_state)
    if not sets:
        conn.close()
        return
    values.append(order_id)
    conn.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id = ?", tuple(values))
    conn.commit()
    conn.close()


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


def list_recent_orders(limit: int = 20) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_order_status(order_id: int, status: str) -> Optional[dict]:
    conn = _get_conn()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def update_order_moysklad(order_id: int, *, moysklad_order_id: Optional[str] = None, sync_error: Optional[str] = None):
    conn = _get_conn()
    sets = []
    values = []
    if moysklad_order_id is not None:
        sets.append("moysklad_order_id = ?")
        values.append(moysklad_order_id)
    if sync_error is not None:
        sets.append("moysklad_sync_error = ?")
        values.append(sync_error)
    if sets:
        values.append(order_id)
        conn.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id = ?", tuple(values))
        conn.commit()
    conn.close()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["items"] = json.loads(d["items"])
    return d
