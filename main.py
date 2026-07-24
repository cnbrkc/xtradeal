"""
Ana giriş noktası — GitHub Actions ve CLI için.
Kullanım:
    python main.py              # Tarama + Telegram
    python main.py --no-telegram  # Sadece tarama (Telegram'a gönderme)
    python main.py --debug      # Debug modu (ham post'ları yazdır)
"""
import sys
import json

from config import Config
from scraper import DonanimHaberScraper
from extractor import extract_deal
from database import Database
from telegram_bot import TelegramNotifier


def run_scan(config: Config, send_telegram: bool = True, debug: bool = False) -> dict:
    print("=" * 60)
    print("  ARAÇ TEKLİF BOTU — Tarama Başlıyor")
    print("=" * 60)

    # Bileşenleri başlat
    scraper = DonanimHaberScraper(
        base_url=config.FORUM_URL,
        user_agent=config.USER_AGENT,
        delay=config.REQUEST_DELAY,
    )
    db = Database(config.DB_PATH)

    # 1) Forumu tara
    print("\n[1/4] Forum sayfaları taranıyor...")
    posts = scraper.scrape(num_pages=config.SCAN_PAGES)
    print(f"      → {len(posts)} post bulundu.")

    if debug:
        for p in posts[:5]:
            print(f"\n--- POST {p.post_id} (sayfa {p.page}) ---")
            print(f"Author: {p.author}")
            print(f"Content: {p.content[:200]}")

    # 2) Araç bilgisi çıkar
    print("\n[2/4] Araç bilgileri çıkarılıyor...")
    deals = []
    for post in posts:
        deal = extract_deal(post)
        # En az marka veya fiyat varsa kaydet
        if deal.car_brand or deal.price:
            deals.append(deal)
    print(f"      → {len(deals)} potansiyel teklif bulundu.")

    # 3) Veritabanına kaydet
    print("\n[3/4] Veritabanına kaydediliyor...")
    new_count = 0
    for deal in deals:
        if db.save_deal(deal):
            new_count += 1
    print(f"      → {new_count} yeni kayıt eklendi.")

    # 4) Telegram'a gönder
    sent_count = 0
    if send_telegram and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        print("\n[4/4] Telegram'a gönderiliyor...")
        notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        unsent = db.get_unsent_deals(min_confidence=config.MIN_CONFIDENCE)
        print(f"      → {len(unsent)} gönderilecek teklif.")

        for deal_dict in unsent:
            msg = notifier.format_deal(deal_dict)
            if notifier.send_message(msg):
                db.mark_sent(deal_dict["post_id"])
                sent_count += 1

        notifier.send_summary(
            total=len(posts), new=new_count, sent=sent_count
        )
        print(f"      → {sent_count} mesaj gönderildi.")
    else:
        print("\n[4/4] Telegram atlandı (token/chat_id yok veya --no-telegram).")

    result = {
        "total_posts": len(posts),
        "potential_deals": len(deals),
        "new_deals": new_count,
        "sent": sent_count,
    }

    print("\n" + "=" * 60)
    print(f"  TAMAMLANDI: {json.dumps(result, ensure_ascii=False)}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    config = Config()

    send_tg = "--no-telegram" not in sys.argv
    debug = "--debug" in sys.argv

    if not config.FORUM_URL:
        print("HATA: FORUM_URL ayarlı değil!")
        sys.exit(1)

    run_scan(config, send_telegram=send_tg, debug=debug)
