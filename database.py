"""
SQLite veritabanı — tüm kolonlar, migration, toplu kayıt destekli.
"""

import sqlite3
import os
from typing import List, Optional
from datetime import datetime


class Database:

    def __init__(self, db_path: str):
        self.db_path = db_path
        d = os.path.dirname(db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS deals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id         TEXT    UNIQUE,
                    author          TEXT,
                    timestamp       TEXT,
                    content         TEXT,
                    url             TEXT,
                    page            INTEGER DEFAULT 0,
                    car_brand       TEXT,
                    car_model       TEXT,
                    price           INTEGER,
                    price_text      TEXT,
                    dealer          TEXT,
                    year            TEXT,
                    confidence      REAL,
                    list_price      INTEGER DEFAULT 0,
                    list_price_text TEXT    DEFAULT '',
                    discount_text   TEXT    DEFAULT '',
                    scanned_at      TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS sent_posts (
                    post_id TEXT UNIQUE,
                    sent_at TEXT
                )
            """)

            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_deals_confidence
                ON deals(confidence DESC)
            """)

            # ── Migration: eski tabloda eksik kolon varsa ekle ──
            migrations = [
                ("page",            "INTEGER", "0"),
                ("list_price",      "INTEGER", "0"),
                ("list_price_text", "TEXT",    "''"),
                ("discount_text",   "TEXT",    "''"),
            ]
            for col, typ, default in migrations:
                try:
                    c.execute(
                        f"ALTER TABLE deals ADD COLUMN {col} {typ} DEFAULT {default}"
                    )
                except sqlite3.OperationalError:
                    pass  # kolon zaten var

    # ──────────────────────────────────────────────
    #  Gönderildi mi?
    # ──────────────────────────────────────────────
    def is_sent(self, post_id: str) -> bool:
        with self._conn() as c:
            r = c.execute(
                "SELECT 1 FROM sent_posts WHERE post_id = ?", (post_id,)
            )
            return r.fetchone() is not None

    # ──────────────────────────────────────────────
    #  Gönderildi olarak işaretle
    # ──────────────────────────────────────────────
    def mark_sent(self, post_id: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO sent_posts VALUES (?, ?)",
                (post_id, datetime.now().isoformat()),
            )

    # ──────────────────────────────────────────────
    #  Tek kayıt ekle (duplicate ise atla)
    # ──────────────────────────────────────────────
    def save_deal(self, deal) -> bool:
        """True = yeni eklendi, False = zaten vardı."""
        with self._conn() as c:
            try:
                c.execute(
                    """INSERT INTO deals
                       (post_id, author, timestamp, content, url, page,
                        car_brand, car_model, price, price_text,
                        dealer, year, confidence,
                        list_price, list_price_text, discount_text,
                        scanned_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        deal.post_id,
                        deal.author,
                        deal.timestamp,
                        deal.content,
                        deal.url,
                        deal.page,
                        deal.car_brand,
                        deal.car_model,
                        deal.price,
                        deal.price_text,
                        deal.dealer,
                        deal.year,
                        deal.confidence,
                        deal.list_price,
                        deal.list_price_text,
                        deal.discount_text,
                        datetime.now().isoformat(),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    # ──────────────────────────────────────────────
    #  Tüm teklifleri getir
    # ──────────────────────────────────────────────
    def get_all_deals(self, limit: int = 200,
                      min_confidence: float = 0.0,
                      brand: Optional[str] = None) -> List[dict]:
        q = "SELECT * FROM deals WHERE confidence >= ?"
        params: list = [min_confidence]
        if brand:
            q += " AND car_brand LIKE ?"
            params.append(f"%{brand}%")
        q += " ORDER BY scanned_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, params).fetchall()]

    # ──────────────────────────────────────────────
    #  Henüz gönderilmemiş teklifler
    # ──────────────────────────────────────────────
    def get_unsent_deals(self, min_confidence: float = 0.3) -> List[dict]:
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute(
                    """SELECT * FROM deals
                       WHERE confidence >= ?
                         AND post_id NOT IN
                             (SELECT post_id FROM sent_posts)
                       ORDER BY confidence DESC""",
                    (min_confidence,),
                ).fetchall()
            ]

    # ──────────────────────────────────────────────
    #  İstatistikler
    # ──────────────────────────────────────────────
    def get_stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
            high = c.execute(
                "SELECT COUNT(*) FROM deals WHERE confidence >= 0.5"
            ).fetchone()[0]
            sent = c.execute(
                "SELECT COUNT(*) FROM sent_posts"
            ).fetchone()[0]
            return {"total": total, "high_confidence": high, "sent": sent}
