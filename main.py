"""
Ana giriş noktası — Sayfa sayfa tara, buldukça HEMEN gönder.
"""

import sys
import json
from dataclasses import asdict

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

    if state.last_page > 0:
        print(f"\n[STATE] Kaldığım yer: sayfa {state.last_page}, "
              f"son post: {state.last_post_id}, "
              f"{state.scan_count}. tarama.")
    else:
        print(f"\n[STATE] İlk çalışma, son sayfadan başlayacağım.")

    # ── Bileşenleri başlat ──
    scraper = DonanimHaberScraper(
        base_url=config.FORUM_URL,
        user_agent=config.USER_AGENT,
        delay=config.REQUEST_DELAY,
        dh_username=config.DH_USERNAME,
        dh_password=config.DH_PASSWORD,
    )
    db = Database(config.DB_PATH)

    notifier = None
    if send_telegram and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        notifier = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
        )

    # ── Sayaçlar ──
    counters = {
        "total_posts": 0,
        "deals_found": 0,
        "new_deals": 0,
        "sent": 0,
        "noise": 0,
    }

    # ──────────────────────────────────────────────
    #  ✅ HER SAYFA BİTİNCE ÇAĞRILAN FONKSİYON
    #  Tara → Çıkar → Kaydet → HEMEN Gönder
    # ──────────────────────────────────────────────
    def handle_page(posts, page_num, total_pages):
        counters["total_posts"] += len(posts)

        for post in posts:
            deal = extract_deal(post)

            # Gürültü filtresi
            if deal.confidence < config.MIN_CONFIDENCE:
                counters["noise"] += 1
                if debug:
                    print(f"     [ELENEN] conf={deal.confidence} "
                          f"→ {post.content[:60]}...")
                continue

            counters["deals_found"] += 1

            # DB'ye kaydet (duplicate ise False döner)
            is_new = db.save_deal(deal)
            if not is_new:
                continue

            counters["new_deals"] += 1
            print(f"     🆕 YENİ: {deal.car_brand} {deal.car_model} "
                  f"| {deal.price_text or deal.price} "
                  f"| conf={deal.confidence}")

            # ✅ HEMEN Telegram'a gönder (tarih sıralı)
            if notifier:
                msg = notifier.format_deal(asdict(deal))
                if notifier.send_message(msg):
                    db.mark_sent(deal.post_id)
                    counters["sent"] += 1

    # ── 1-3) Tara + Çıkar + Gönder (hepsi bir arada) ──
    print(f"\n[1/3] Forum taranıyor, buldukça gönderilecek...")
    posts, total_pages, last_post_id = scraper.scrape_latest(
        num_pages=config.SCAN_PAGES,
        last_page=state.last_page,
        on_page=handle_page,
    )

    # ── 4) Özet ──
    print(f"\n[2/3] Özet çıkarılıyor...")
    print(f"      Toplam post:    {counters['total_posts']}")
    print(f"      Teklif bulundu: {counters['deals_found']}")
    print(f"      Yeni kayıt:     {counters['new_deals']}")
    print(f"      Gürültü elendi: {counters['noise']}")
    print(f"      Gönderilen:     {counters['sent']}")

    # ── Yeni bir şey yoksa bildir ──
    if notifier and counters["new_deals"] == 0:
        print(f"\n[3/3] Yeni teklif yok, bildiriliyor...")
        if total_pages > state.last_page:
            # Yeni sayfa var ama teklif yok
            notifier.send_message(
                f"📭 <b>Yeni teklif yok</b>\n\n"
                f"Sayfa {state.last_page} → {total_pages} tarandı, "
                f"{counters['total_posts']} post incelendi.\n"
                f"Yeni araç teklifi bulunamadı."
            )
        else:
            # Yeni sayfa da yok
            notifier.send_message(
                f"📭 <b>Yeni teklif yok</b>\n\n"
                f"Sayfa {total_pages} tarandı, "
                f"{counters['total_posts']} post incelendi.\n"
                f"Yeni sayfa eklenmemiş, yeni teklif yok."
            )
    elif notifier and counters["sent"] > 0:
        notifier.send_summary(
            total=counters["total_posts"],
            new=counters["new_deals"],
            sent=counters["sent"],
        )

    # ── State'i kaydet ──
    new_last_page = total_pages if total_pages > 0 else state.last_page
    state_mgr.update(
        last_page=new_last_page,
        last_post_id=last_post_id,
        total_pages=total_pages,
    )
    print(f"\n[STATE] ✅ Kaydedildi → "
          f"son sayfa: {new_last_page}/{total_pages}, "
          f"son post: {last_post_id}")

    # ── Sonuç ──
    result = {
        "total_posts": counters["total_posts"],
        "potential_deals": counters["deals_found"],
        "new_deals": counters["new_deals"],
        "sent": counters["sent"],
        "noise_filtered": counters["noise"],
        "last_page": new_last_page,
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
