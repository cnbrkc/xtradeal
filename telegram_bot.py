"""
Telegram bildirim botu — Tam mesaj + bayi fiyatı karşılaştırması.
"""

import requests
import time


class TelegramNotifier:

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                time.sleep(1)  # rate limit
                return True
            else:
                print(f"[TG] Hata {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[TG] Gönderim hatası: {e}")
            return False

    def format_deal(self, deal: dict) -> str:
        """Tek bir teklifi güzel formatla. MESAJIN TAMAMINI gösterir."""

        brand = deal.get("car_brand", "") or "?"
        model = deal.get("car_model", "") or ""
        price = deal.get("price", 0)
        price_text = deal.get("price_text", "")
        list_price = deal.get("list_price", 0)
        list_price_text = deal.get("list_price_text", "")
        discount_text = deal.get("discount_text", "")
        dealer = deal.get("dealer", "")
        year = deal.get("year", "")
        author = deal.get("author", "")
        timestamp = deal.get("timestamp", "")
        content = deal.get("content", "")
        url = deal.get("url", "")
        confidence = deal.get("confidence", 0)
        page = deal.get("page", 0)

        # Başlık
        title = f"🚗 {brand} {model}".strip()
        if year:
            title += f" ({year})"

        lines = [f"<b>{title}</b>", ""]

        # Fiyat bilgisi
        if price:
            lines.append(f"💰 <b>Teklif Fiyatı:</b> {price:,.0f} TL")
            if price_text:
                lines.append(f"   <i>({price_text})</i>")

        # Bayi / liste fiyatı
        if list_price:
            lines.append(f"🏷️ <b>Bayi Liste Fiyatı:</b> {list_price:,.0f} TL")
            if list_price_text:
                lines.append(f"   <i>({list_price_text})</i>")

        # İndirim
        if discount_text:
            lines.append(f"📉 <b>İndirim:</b> {discount_text}")

        # Bayi
        if dealer:
            lines.append(f"🏢 <b>Bayi:</b> {dealer}")

        # Yazar ve tarih
        meta = []
        if author:
            meta.append(f"👤 {author}")
        if timestamp:
            meta.append(f"🕐 {timestamp}")
        if page:
            meta.append(f"📄 Sayfa {page}")
        if meta:
            lines.append("")
            lines.append(" | ".join(meta))

        # ── MESAJIN TAMAMI ──
        lines.append("")
        lines.append("─" * 30)
        lines.append("📝 <b>Forum Mesajı:</b>")
        lines.append("")

        # Telegram 4096 karakter limiti var, güvenli kes
        # Başlık kısmı ~500 karakter, mesaj için ~3400 bırak
        max_content = 3400
        if len(content) > max_content:
            lines.append(content[:max_content] + "...")
        else:
            lines.append(content)

        lines.append("")
        lines.append("─" * 30)

        # Güven skoru
        conf_bar = "🟢" if confidence >= 0.7 else "🟡" if confidence >= 0.5 else "🔴"
        lines.append(f"{conf_bar} Güven: %{int(confidence * 100)}")

        # Link
        if url:
            lines.append(f"🔗 <a href=\"{url}\">Forum'da Gör</a>")

        return "\n".join(lines)

    def send_summary(self, total: int, new: int, sent: int) -> bool:
        msg = (
            f"📊 <b>Tarama Özeti</b>\n\n"
            f"📄 Taranan post: {total}\n"
            f"🆕 Yeni kayıt: {new}\n"
            f"📤 Gönderilen: {sent}\n"
        )
        return self.send_message(msg)
