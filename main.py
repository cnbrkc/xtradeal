"""
Ana giriş noktası — State destekli, tersten tarama, sıkı filtreleme.
"""

import sys
import json

from config import Config
from scraper import DonanimHaberScraper
from extractor import extract_deal
from database import Database
from telegram_bot import TelegramNotifier
from state_manager import StateManager


def run_scan(config: Config, send_telegram: bool = True,
             debug: bool = False) -> dict:

    print("=" * 60)
    print("  ARAÇ TEKLİF BOTU — Tarama Başlıyor")
    print("=" * 60)

    # ── State yükle ──
    state_mgr = StateManager()
    state = state_mgr.load()
    print(f"\n[STATE] Son tarama: sayfa {state.last_page}, "
          f"toplam {state.scan_count} tarama yapılmış")

    # ── Bileşenleri başlat ──
    scraper = DonanimHaberScraper(
        base_url=config.FORUM_URL,
        user_agent=config.USER_AGENT,
        delay=config.REQUEST_DELAY,
        dh_username=config.DH_USERNAME,
        dh_password=config.DH_PASSWORD,
    )
    db = Database(config.DB_PATH)

    # ── 1) Forumu tara (SON SAYFADAN GERİYE) ──
    print(f"\n[1/4] Forum taranıyor (son {config.SCAN_PAGES} sayfa)...")
    posts, last_page, total_pages = scraper.scrape_latest(
        num_pages=config.SCAN_PAGES,
        start_page=state.last_page,
    )
    print(f"      → {len(posts)} post bulundu.")

    if not posts:
        print("      ⚠️ Post bulunamadı!")
        state_mgr.update(last_page=last_page, total_pages=total_pages)
        return {"total_posts": 0, "potential_deals": 0,
                "new_deals": 0, "sent": 0}

    # ── 2) Araç bilgisi çıkar (SIKI FİLTRE) ──
    print(f"\n[2/4] Araç bilgileri çıkarılıyor...")
    deals = []
    for post in posts:
        deal = extract_deal(post)
        # ✅ Sadece confidence >= MIN_CONFIDENCE olanları al
        if deal.confidence >= config.MIN_CONFIDENCE:
            deals.append(deal)
        elif debug:
            print(f"      [ELENEN] conf={deal.confidence} "
                  f"brand={deal.car_brand} price={deal.price} "
                  f"→ {post.content[:80]}...")
    print(f"      → {len(deals)} teklif bulundu "
          f"({len(posts) - len(deals)} gürültü elendi).")

    # ── 3) Veritabanına kaydet ──
    print(f"\n[3/4] Veritabanına kaydediliyor...")
    new_count = 0
    for deal in deals:
        if db.save_deal(deal):
            new_count += 1
    print(f"      → {new_count} yeni kayıt "
          f"({len(deals) - new_count} duplicate atlandı).")

    # ── 4) Telegram'a gönder ──
    sent_count = 0
    if send_telegram and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        print(f"\n[4/4] Telegram'a gönderiliyor...")
        notifier = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
        )
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
        print(f"\n[4/4] Telegram atlandı.")

    # ── State'i kaydet ──
    last_post_id = posts[0].post_id if posts else ""
    state_mgr.update(
        last_page=last_page,
        last_post_id=last_post_id,
        total_pages=total_pages,
    )
    print(f"\n[STATE] Kaydedildi → sayfa: {last_page}, post: {last_post_id}")

    # ── Özet ──
    result = {
        "total_posts": len(posts),
        "potential_deals": len(deals),
        "new_deals": new_count,
        "sent": sent_count,
        "last_page": last_page,
        "total_pages": total_pages,
    }
    print(f"\n{'=' * 60}")
    print(f"  TAMAMLANDI: {json.dumps(result, ensure_ascii=False)}")
    print(f"{'=' * 60}")
    return result


if __name__ == "__main__":
    config = Config()
    send_tg = "--no-telegram" not in sys.argv
    debug = "--debug" in sys.argv

    if not config.FORUM_URL:
        print("HATA: FORUM_URL ayarlı değil!")
        sys.exit(1)

    run_scan(config, send_telegram=send_tg, debug=debug)
