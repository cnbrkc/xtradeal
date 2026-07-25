"""
SQLite veritabanı yönetimi.
Teklifleri saklar, duplicate (aynı post) kontrolü yapar.
"""

import sqlite3
import os
from typing import List


class Database:

    def __init__(self, db_path: str = "data/deals.db"):
        # data/ klasörü yoksa oluştur
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        """Tablo yoksa oluştur."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id     TEXT    UNIQUE NOT NULL,
                author      TEXT    DEFAULT '',
                timestamp   TEXT    DEFAULT '',
                brand       TEXT    DEFAULT '',
                model       TEXT    DEFAULT '',
                year        TEXT    DEFAULT '',
                price       TEXT    DEFAULT '',
                confidence  REAL    DEFAULT 0.0,
                content     TEXT    DEFAULT '',
                url         TEXT    DEFAULT '',
                page        INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self.conn.commit()

    # ──────────────────────────────────────────────
    #  Teklifleri kaydet (duplicate olanları atla)
    # ──────────────────────────────────────────────
    def save_deals(self, deals) -> list:
        """
        Yeni teklifleri kaydet.
        post_id zaten varsa → duplicate → sessizce atla.
        Sadece YENİ eklenenleri döndür.
        """
        new_deals = []
        skipped = 0

        for deal in deals:
            try:
                self.conn.execute(
                    """INSERT INTO deals
                       (post_id, author, timestamp, brand, model, year,
                        price, confidence, content, url, page)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        deal.post_id,
                        deal.author,
                        deal.timestamp,
                        deal.brand,
                        deal.model,
                        deal.year,
                        deal.price,
                        deal.confidence,
                        deal.content,
                        deal.url,
                        deal.page,
                    )
                )
                new_deals.append(deal)
            except sqlite3.IntegrityError:
                # post_id zaten var → duplicate, atla
                skipped += 1

        self.conn.commit()

        if skipped > 0:
            print(f"      [DB] {skipped} duplicate atlandı.")

        return new_deals

    # ──────────────────────────────────────────────
    #  Tüm teklifleri getir
    # ──────────────────────────────────────────────
    def get_all_deals(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM deals ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ──────────────────────────────────────────────
    #  Toplam kayıt sayısı
    # ──────────────────────────────────────────────
    def get_deal_count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM deals")
        return cursor.fetchone()[0]

    # ──────────────────────────────────────────────
    #  Belirli bir post_id var mı?
    # ──────────────────────────────────────────────
    def exists(self, post_id: str) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM deals WHERE post_id = ?", (post_id,)
        )
        return cursor.fetchone() is not None

    # ──────────────────────────────────────────────
    #  Kapat
    # ──────────────────────────────────────────────
    def close(self):
        self.conn.close()
