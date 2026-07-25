"""
Ana giriş noktası — State destekli, tersten tarama.
"""

import os
import sys
import json
import logging
from datetime import datetime

from scraper import DonanimHaberScraper
from extractor import CarInfoExtractor
from database import Database
from notifier import TelegramNotifier
from state_manager import StateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    # ── Yapılandırma ──
    forum_url = os.environ.get(
        "FORUM_URL",
        "https://forum.donanimhaber.com/sifir-arac-ve-arac-fiyati-teklifi-alanlar-2022--132918743"
    )
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    dh_username = os.environ.get("DH_USERNAME", "")
    dh_password = os.environ.get("DH_PASSWORD", "")
    scan_pages = int(os.environ.get("SCAN_PAGES", "5"))
    db_path = os.environ.get("DB_PATH", "data/deals.db")
    request_delay = float(os.environ.get("REQUEST_DELAY", "2.0"))
    min_confidence = float(os.environ.get("MIN_CONFIDENCE", "0.3"))

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    print("=" * 60)
    print("  ARAÇ TEKLİF BOTU — Tarama Başlıyor")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── State yükle ──
    state_mgr = StateManager()
    state = state_mgr.load()
    print(f"\n[STATE] Son tarama: sayfa {state.last_page}, "
          f"post {state.last_post_id}, "
          f"toplam {state.scan_count} tarama yapılmış")

    # ── 1) Forum'u tara (SON SAYFADAN GERİYE) ──
    print(f"\n[1/4] Forum sayfaları taranıyor (son {scan_pages} sayfa)...")
    scraper = DonanimHaberScraper(
        base_url=forum_url,
        user_agent=user_agent,
        delay=request_delay,
        dh_username=dh_username,
        dh_password=dh_password,
    )

    # ✅ State'den başla: ilk çalışmada 0 (en son sayfa),
    # sonraki çalışmalarda kaldığı yerden
    start_page = state.last_page  # 0 ise en sondan başlar

    posts, last_scanned_page, total_pages = scraper.scrape_latest(
        num_pages=scan_pages,
        start_page=start_page,
    )
    print(f"      → {len(posts)} post bulundu.")

    if not posts:
        print("      ⚠️ Hiç post bulunamadı, çıkılıyor.")
        _save_state(state_mgr, state, last_scanned_page, "", total_pages)
        return

    # ── 2) Araç bilgilerini çıkar ──
    print(f"\n[2/4] Araç bilgileri çıkarılıyor...")
    extractor = CarInfoExtractor(min_confidence=min_confidence)
    deals = extractor.extract_from_posts(posts)
    print(f"      → {len(deals)} potansiyel teklif bulundu.")

    # ── 3) Veritabanına kaydet (duplicate kontrolü burada) ──
    print(f"\n[3/4] Veritabanına kaydediliyor...")
    db = Database(db_path)
    new_deals = db.save_deals(deals)
    print(f"      → {len(new_deals)} YENİ kayıt eklendi "
          f"({len(deals) - len(new_deals)} duplicate atlandı).")

    # ── 4) Telegram'a gönder (sadece YENİ olanları) ──
    print(f"\n[4/4] Telegram'a gönderiliyor...")
    if telegram_token and telegram_chat_id and new_deals:
        notifier = TelegramNotifier(telegram_token, telegram_chat_id)
        sent = notifier.send_deals(new_deals)
        print(f"      → {sent} mesaj gönderildi.")
    else:
        sent = 0
        if not new_deals:
            print("      → Gönderilecek YENİ teklif yok (hepsi daha önce gönderilmiş).")
        elif not telegram_token:
            print("      → Telegram token yok, atlanıyor.")

    # ── State'i kaydet ──
    last_post_id = posts[0].post_id if posts else ""
    _save_state(state_mgr, state, last_scanned_page, last_post_id, total_pages)

    # ── Özet ──
    summary = {
        "total_posts": len(posts),
        "potential_deals": len(deals),
        "new_deals": len(new_deals),
        "sent": sent,
        "last_page": last_scanned_page,
        "total_pages": total_pages,
    }
    print(f"\n{'=' * 60}")
    print(f"  TAMAMLANDI: {json.dumps(summary, ensure_ascii=False)}")
    print(f"{'=' * 60}")


def _save_state(state_mgr, state, last_page, last_post_id, total_pages):
    """State'i güncelle ve kaydet."""
    state_mgr.update(
        last_page=last_page,
        last_post_id=last_post_id,
        total_pages=total_pages,
    )
    print(f"\n[STATE] Kaydedildi → sayfa: {last_page}, "
          f"post: {last_post_id}, toplam sayfa: {total_pages}")


if __name__ == "__main__":
    main()
