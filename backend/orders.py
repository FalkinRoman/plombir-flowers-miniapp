"""
Хранение и управление заказами — SQLite.
"""
import sqlite3
import json
import datetime
import os
import hashlib
import secrets
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES admin_users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tilda_key TEXT NOT NULL UNIQUE,
            ms_href TEXT NOT NULL,
            ms_type TEXT NOT NULL DEFAULT 'assortment',
            ms_id TEXT,
            ms_name TEXT,
            note TEXT,
            updated_by TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ms_assortment_cache (
            ms_id TEXT PRIMARY KEY,
            ms_href TEXT NOT NULL,
            ms_type TEXT NOT NULL,
            name TEXT,
            code TEXT,
            external_code TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
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


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    )
    return digest.hex()


def create_or_update_admin_user(*, email: str, password: str, role: str = "admin", is_active: bool = True):
    email_n = (email or "").strip().lower()
    if not email_n:
        raise ValueError("email required")
    if role not in {"superadmin", "admin", "manager"}:
        role = "admin"
    if len(password or "") < 8:
        raise ValueError("password too short")

    conn = _get_conn()
    now = _now_iso()
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    existing = conn.execute("SELECT id FROM admin_users WHERE email = ?", (email_n,)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE admin_users
               SET password_hash = ?, password_salt = ?, role = ?, is_active = ?, updated_at = ?
             WHERE id = ?
            """,
            (password_hash, salt, role, 1 if is_active else 0, now, int(existing["id"])),
        )
    else:
        conn.execute(
            """
            INSERT INTO admin_users (email, password_hash, password_salt, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email_n, password_hash, salt, role, 1 if is_active else 0, now, now),
        )
    conn.commit()
    conn.close()


def ensure_superadmin(*, email: str, password: str):
    conn = _get_conn()
    has_superadmin = conn.execute(
        "SELECT id FROM admin_users WHERE role = 'superadmin' AND is_active = 1 LIMIT 1"
    ).fetchone()
    conn.close()
    if has_superadmin:
        return
    create_or_update_admin_user(email=email, password=password, role="superadmin", is_active=True)


def authenticate_admin(email: str, password: str) -> Optional[dict]:
    email_n = (email or "").strip().lower()
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT id, email, password_hash, password_salt, role, is_active
          FROM admin_users
         WHERE email = ?
         LIMIT 1
        """,
        (email_n,),
    ).fetchone()
    conn.close()
    if not row or int(row["is_active"] or 0) != 1:
        return None
    check = _hash_password(password or "", str(row["password_salt"]))
    if check != str(row["password_hash"]):
        return None
    return {
        "id": int(row["id"]),
        "email": str(row["email"]),
        "role": str(row["role"] or "admin"),
    }


def create_admin_session(user_id: int, ttl_seconds: int = 86400) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = (now + datetime.timedelta(seconds=max(60, int(ttl_seconds)))).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO admin_sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, int(user_id), expires_at, now.isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def get_admin_by_session(token: str) -> Optional[dict]:
    t = (token or "").strip()
    if not t:
        return None
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT s.token, s.expires_at, u.id, u.email, u.role, u.is_active
          FROM admin_sessions s
          JOIN admin_users u ON u.id = s.user_id
         WHERE s.token = ?
         LIMIT 1
        """,
        (t,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    try:
        exp = datetime.datetime.fromisoformat(str(row["expires_at"]))
    except ValueError:
        exp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    now = datetime.datetime.now(datetime.timezone.utc)
    if exp <= now or int(row["is_active"] or 0) != 1:
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (t,))
        conn.commit()
        conn.close()
        return None
    conn.close()
    return {
        "id": int(row["id"]),
        "email": str(row["email"]),
        "role": str(row["role"] or "admin"),
        "token": t,
    }


def delete_admin_session(token: str):
    conn = _get_conn()
    conn.execute("DELETE FROM admin_sessions WHERE token = ?", ((token or "").strip(),))
    conn.commit()
    conn.close()


def list_admin_users() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, email, role, is_active, created_at, updated_at FROM admin_users ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_product_mapping(
    *,
    tilda_key: str,
    ms_href: str,
    ms_type: str = "assortment",
    ms_id: Optional[str] = None,
    ms_name: Optional[str] = None,
    note: Optional[str] = None,
    updated_by: Optional[str] = None,
):
    key = (tilda_key or "").strip()
    if not key:
        raise ValueError("tilda_key required")
    href = (ms_href or "").strip()
    if not href:
        raise ValueError("ms_href required")
    t = (ms_type or "assortment").strip()
    now = _now_iso()
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO product_mappings (tilda_key, ms_href, ms_type, ms_id, ms_name, note, updated_by, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tilda_key) DO UPDATE SET
            ms_href = excluded.ms_href,
            ms_type = excluded.ms_type,
            ms_id = excluded.ms_id,
            ms_name = excluded.ms_name,
            note = excluded.note,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        (
            key,
            href,
            t,
            (ms_id or "").strip() or None,
            (ms_name or "").strip() or None,
            (note or "").strip() or None,
            (updated_by or "").strip() or None,
            now,
        ),
    )
    conn.commit()
    conn.close()


def get_product_mapping_meta(*keys: str) -> Optional[dict]:
    prepared = [str(k or "").strip() for k in keys if str(k or "").strip()]
    if not prepared:
        return None
    conn = _get_conn()
    placeholders = ",".join(["?"] * len(prepared))
    row = conn.execute(
        f"""
        SELECT tilda_key, ms_href, ms_type, ms_id, ms_name, updated_at
          FROM product_mappings
         WHERE tilda_key IN ({placeholders})
         ORDER BY updated_at DESC
         LIMIT 1
        """,
        tuple(prepared),
    ).fetchone()
    conn.close()
    if not row:
        return None
    href = str(row["ms_href"] or "").strip()
    mtype = str(row["ms_type"] or "assortment").strip()
    if not href:
        return None
    return {
        "href": href,
        "type": mtype,
        "mediaType": "application/json",
        "mapping_key": str(row["tilda_key"]),
        "mapping_ms_name": str(row["ms_name"] or ""),
    }


def list_product_mappings(limit: int = 500, search: str = "") -> list[dict]:
    lim = max(1, min(int(limit), 5000))
    q = f"%{(search or '').strip().lower()}%"
    conn = _get_conn()
    if q == "%%":
        rows = conn.execute(
            """
            SELECT id, tilda_key, ms_href, ms_type, ms_id, ms_name, note, updated_by, updated_at
              FROM product_mappings
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            (lim,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tilda_key, ms_href, ms_type, ms_id, ms_name, note, updated_by, updated_at
              FROM product_mappings
             WHERE lower(tilda_key) LIKE ? OR lower(coalesce(ms_name, '')) LIKE ? OR lower(coalesce(ms_id, '')) LIKE ?
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            (q, q, q, lim),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_product_mapping(tilda_key: str):
    conn = _get_conn()
    conn.execute("DELETE FROM product_mappings WHERE tilda_key = ?", ((tilda_key or "").strip(),))
    conn.commit()
    conn.close()


def replace_ms_assortment_cache(rows: list[dict]):
    now = _now_iso()
    conn = _get_conn()
    conn.execute("DELETE FROM ms_assortment_cache")
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO ms_assortment_cache
            (ms_id, ms_href, ms_type, name, code, external_code, archived, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (row.get("ms_id") or "").strip(),
                (row.get("ms_href") or "").strip(),
                (row.get("ms_type") or "assortment").strip(),
                (row.get("name") or "").strip(),
                (row.get("code") or "").strip(),
                (row.get("external_code") or "").strip(),
                1 if bool(row.get("archived")) else 0,
                now,
            ),
        )
    conn.commit()
    conn.close()


def search_ms_assortment_cache(query: str = "", limit: int = 200) -> list[dict]:
    lim = max(1, min(int(limit), 1000))
    q = f"%{(query or '').strip().lower()}%"
    conn = _get_conn()
    if q == "%%":
        rows = conn.execute(
            """
            SELECT ms_id, ms_href, ms_type, name, code, external_code, archived, updated_at
              FROM ms_assortment_cache
             ORDER BY name COLLATE NOCASE ASC
             LIMIT ?
            """,
            (lim,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT ms_id, ms_href, ms_type, name, code, external_code, archived, updated_at
              FROM ms_assortment_cache
             WHERE lower(name) LIKE ? OR lower(code) LIKE ? OR lower(external_code) LIKE ? OR lower(ms_id) LIKE ?
             ORDER BY name COLLATE NOCASE ASC
             LIMIT ?
            """,
            (q, q, q, q, lim),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_order_telegram_users(limit: int = 5000) -> list[dict]:
    lim = max(1, min(int(limit), 20000))
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT telegram_user_id, max(customer_name) as customer_name, max(telegram_username) as telegram_username
          FROM orders
         WHERE trim(coalesce(telegram_user_id, '')) <> ''
         GROUP BY telegram_user_id
         ORDER BY max(id) DESC
         LIMIT ?
        """,
        (lim,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
