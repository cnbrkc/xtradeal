import requests
from typing import List


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str) -> bool:
        try:
            r = requests.post(
                f"{self.api}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[TELEGRAM] Error {r.status_code}: {r.text[:200]}")
            return r.status_code == 200
        except Exception as e:
            print(f"[TELEGRAM] Exception: {e}")
            return False

    def format_deal(self, deal: dict) -> str:
        lines = ["🚗 <b>Yeni Araç Teklifi</b>", ""]

        # Araç
        car = deal.get("car_brand") or ""
        if deal.get("car_model"):
            car += f" {deal['car_model']}"
        if deal.get("year"):
            car += f" ({deal['year']})"
        if car:
            lines.append(f"📋 <b>Araç:</b> {car.strip()}")

        # Fiyat
        price = deal.get("price_text") or (
            f"{deal['price']:,} TL".replace(",", ".") if deal.get("price") else None
        )
        if price:
            lines.append(f"💰 <b>Fiyat:</b> {price}")

        # Bayi
        if deal.get("dealer"):
            lines.append(f"🏪 <b>Bayi:</b> {deal['dealer']}")

        # Paylaşan
        if deal.get("author"):
            lines.append(f"👤 <b>Paylaşan:</b> {deal['author']}")

        # Link
        if deal.get("url"):
            lines.append(f'🔗 <a href="{deal["url"]}">Konuya Git</a>')

        # Güven
        conf = int(deal.get("confidence", 0) * 100)
        lines.append(f"📊 <b>Güven:</b> %{conf}")

        # İçerik özeti
        content = (deal.get("content") or "")[:250]
        if content:
            lines.append("")
            lines.append(f"<i>{content}</i>")

        return "\n".join(lines)

    def send_deals(self, deals: List[dict]) -> int:
        sent = 0
        for d in deals:
            if self.send_message(self.format_deal(d)):
                sent += 1
        return sent

    def send_summary(self, total: int, new: int, sent: int):
        self.send_message(
            f"📊 <b>Tarama Tamamlandı</b>\n\n"
            f"📝 Toplam post: {total}\n"
            f"🆕 Yeni teklif: {new}\n"
            f"📤 Gönderilen: {sent}"
        )
