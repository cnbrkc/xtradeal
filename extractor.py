"""
Araç teklif bilgisi çıkarıcı — SIKI filtreleme + bayi fiyatı.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CarDeal:
    post_id: str = ""
    author: str = ""
    timestamp: str = ""
    content: str = ""
    url: str = ""
    page: int = 0
    car_brand: str = ""
    car_model: str = ""
    price: int = 0
    price_text: str = ""
    dealer: str = ""
    year: str = ""
    confidence: float = 0.0
    # Yeni: bayi / liste fiyatı
    list_price: int = 0
    list_price_text: str = ""
    discount_text: str = ""


# ──────────────────────────────────────────────
#  Marka listesi
# ──────────────────────────────────────────────
BRANDS = [
    "toyota", "honda", "hyundai", "renault", "fiat", "ford", "volkswagen",
    "vw", "opel", "peugeot", "citroen", "skoda", "seat", "dacia", "nissan",
    "kia", "mg", "chery", "byd", "tesla", "bmw", "mercedes", "audi",
    "volvo", "cupra", "suzuki", "mitsubishi", "subaru", "mazda",
    "alfa romeo", "jeep", "land rover", "porsche", "lexus", "mini",
    "togg", "geely", "jaecoo", "omoda", "skywell", "seres", "leapmotor",
    "deepal", "avatr", "zeekr", "xpeng", "nio", "hongqi",
]

# Model pattern'ları (marka → regex)
MODEL_PATTERNS = {
    "toyota": r"(corolla|camry|c-hr|chr|rav4|yaris|land cruiser|hilux|corolla cross)",
    "honda": r"(civic|cr-v|crv|hr-v|hrv|jazz|city|accord)",
    "hyundai": r"(i20|i10|tucson|kona|bayon|santa fe|ioniq|elantra)",
    "renault": r"(clio|megane|captur|austral|taliant|duster|express)",
    "fiat": r"(egea|tipo|500|panda|doblo|fiorino)",
    "ford": r"(focus|kuga|puma|fiesta|tourneo|transit|ranger|mustang)",
    "volkswagen": r"(golf|passat|tiguan|polo|t-roc|troc|taigo|id\.|caddy|transporter)",
    "vw": r"(golf|passat|tiguan|polo|t-roc|troc|taigo|id\.|caddy|transporter)",
    "opel": r"(astra|corsa|mokka|grandland|crossland|insignia)",
    "peugeot": r"(208|308|3008|408|5008|2008|508|partner|rifter)",
    "citroen": r"(c3|c4|c5|berlingo|jumpy|jumper)",
    "skoda": r"(octavia|superb|kodiaq|karoq|fabia|scala|kamiq)",
    "seat": r"(leon|ibiza|ateca|arona|tarraco)",
    "dacia": r"(duster|sandero|jogger|logan|spring)",
    "nissan": r"(qashqai|juke|x-trail|micra|leaf|townstar)",
    "kia": r"(sportage|ceed|stonic|picanto|rio|sorento|ev6|ev9|niro)",
    "mg": r"(zs|hs|4|marvel|cyberster)",
    "chery": r"(tiggo|omoda|jaecoo)",
    "byd": r"(atto|seal|han|tang|dolphin|song|yuan)",
    "togg": r"(t10x|t10f|t8x)",
    "bmw": r"(3 serisi|5 serisi|x1|x2|x3|x5|1 serisi|2 serisi|i4|i5|ix)",
    "mercedes": r"(a serisi|c serisi|e serisi|gla|glb|glc|gle|cla|eqa|eqb|eqc)",
    "audi": r"(a3|a4|a5|a6|q2|q3|q5|q7|q8|e-tron|etron)",
    "volvo": r"(xc40|xc60|xc90|s60|s90|v60|v90|ex30|ex40|ex90)",
    "cupra": r"(formentor|born|leon|ateca|tavascan)",
    "suzuki": r"(swift|vitara|s-cross|scross|jimny)",
    "mitsubishi": r"(outlander|asx|eclipse|l200|space star)",
    "jeep": r"(renegade|compass|avenger|wrangler|grand cherokee)",
}

# ──────────────────────────────────────────────
#  Fiyat extraction
# ──────────────────────────────────────────────
def _extract_price(text: str) -> tuple:
    """Metinden TL fiyatı çıkar. (price_int, price_text)"""
    text_lower = text.lower()

    # "1.250.000 TL" / "1,250,000 TL" / "1250000 TL"
    m = re.search(r"(\d{1,3}(?:[.,]\d{3}){1,3}|\d{4,})\s*(?:tl|₺|lira)", text_lower)
    if m:
        raw = m.group(1).replace(".", "").replace(",", "")
        try:
            return int(raw), m.group(0).strip()
        except ValueError:
            pass

    # "1 milyon 250 bin" / "1.25 milyon"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*milyon", text_lower)
    if m:
        val = float(m.group(1).replace(",", "."))
        price = int(val * 1_000_000)
        # "1 milyon 250 bin" → ekstra bin kısmı
        m2 = re.search(r"milyon\s+(\d+)\s*bin", text_lower)
        if m2:
            price += int(m2.group(1)) * 1000
        return price, m.group(0).strip()

    # "250 bin TL" / "250.000"
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})*)\s*bin\s*(?:tl|₺|lira)?", text_lower)
    if m:
        raw = m.group(1).replace(".", "").replace(",", "")
        try:
            return int(raw) * 1000, m.group(0).strip()
        except ValueError:
            pass

    return 0, ""


def _extract_list_price(text: str) -> tuple:
    """Bayi / liste fiyatını çıkar."""
    text_lower = text.lower()

    # "bayi fiyatı: 1.350.000 TL" / "liste fiyatı 1.400.000"
    patterns = [
        r"(?:bayi|liste|anahtar\s*teslim|katalog)\s*(?:fiyat[ıi]?|fiyatı)?[:\s]*"
        r"(\d{1,3}(?:[.,]\d{3}){1,3}|\d{4,})\s*(?:tl|₺|lira)?",
        r"(?:bayi|liste|anahtar\s*teslim|katalog)\s*(?:fiyat[ıi]?|fiyatı)?[:\s]*"
        r"(\d+(?:[.,]\d+)?)\s*milyon",
    ]
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            try:
                val = int(raw)
                if val < 10000:  # "1.4 milyon" → 1.4
                    val = int(float(raw.replace(",", ".")) * 1_000_000)
                return val, m.group(0).strip()
            except ValueError:
                pass
    return 0, ""


def _extract_dealer(text: str) -> str:
    """Bayi / yetkili satıcı adı çıkar."""
    text_lower = text.lower()
    m = re.search(
        r"([\wçğıöşüÇĞİÖŞÜ]+(?:\s+[\wçğıöşüÇĞİÖŞÜ]+)*)\s+"
        r"(?:bayi|yetkili\s+satıcı|plaza|otomotiv|oto|motorlu)",
        text_lower
    )
    if m:
        return m.group(0).strip().title()
    return ""


def _extract_year(text: str) -> str:
    m = re.search(r"(20[12]\d)\s*(?:model|yıl|kasa)?", text)
    if m:
        return m.group(1)
    return ""


# ──────────────────────────────────────────────
#  Ana extraction fonksiyonu — SIKI filtreleme
# ──────────────────────────────────────────────
def extract_deal(post) -> CarDeal:
    """
    Bir ForumPost'tan araç teklif bilgisi çıkar.
    Sadece GERÇEK teklifleri yakalar, gürültüyü eler.
    """
    text = post.content
    text_lower = text.lower()

    deal = CarDeal(
        post_id=post.post_id,
        author=post.author,
        timestamp=post.timestamp,
        content=text,
        url=post.url,
        page=post.page,
    )

    # ── 1) Marka bul ──
    for brand in BRANDS:
        if re.search(r"\b" + re.escape(brand) + r"\b", text_lower):
            deal.car_brand = brand.title()
            # Model bul
            if brand in MODEL_PATTERNS:
                m = re.search(MODEL_PATTERNS[brand], text_lower)
                if m:
                    deal.car_model = m.group(1).title()
            break

    # ── 2) Fiyat bul ──
    deal.price, deal.price_text = _extract_price(text)

    # ── 3) Bayi / liste fiyatı bul ──
    deal.list_price, deal.list_price_text = _extract_list_price(text)

    # ── 4) Bayi adı ──
    deal.dealer = _extract_dealer(text)

    # ── 5) Yıl ──
    deal.year = _extract_year(text)

    # ── 6) İndirim hesapla ──
    if deal.price and deal.list_price and deal.list_price > 0:
        diff = deal.list_price - deal.price
        pct = (diff / deal.list_price) * 100
        deal.discount_text = f"{diff:,.0f} TL indirim (%{pct:.1f})"

    # ── 7) Confidence scoring — SIKI ──
    score = 0.0

    # Marka + model varsa güçlü sinyal
    if deal.car_brand and deal.car_model:
        score += 0.35
    elif deal.car_brand:
        score += 0.15

    # Fiyat varsa güçlü sinyal
    if deal.price > 0:
        score += 0.35

    # Bayi/liste fiyatı varsa ekstra
    if deal.list_price > 0:
        score += 0.15

    # Bayi adı varsa
    if deal.dealer:
        score += 0.10

    # Anahtar kelimeler
    keywords = ["teklif", "fiyat", "bayi", "sıfır", "sifir", "araç", "arac",
                "kampanya", "indirim", "anahtar teslim", "liste fiyat",
                "peşin", "pesin", "kredi", "takas", "plaka", "teslim"]
    kw_count = sum(1 for kw in keywords if kw in text_lower)
    score += min(kw_count * 0.05, 0.20)

    # ── GÜRÜLTÜ FİLTRESİ ──
    # Fiyat YOKSA ve marka/model YOKSA → çöp
    if deal.price == 0 and not (deal.car_brand and deal.car_model):
        score = 0.0

    # Çok kısa mesajlar → çöp
    if len(text) < 30:
        score = 0.0

    # Sadece soru soran mesajlar → çöp
    question_words = ["alan var mı", "var mı", "ne kadar", "kaç para",
                      "önerir misiniz", "tavsiye", "yorum", "deneyim"]
    if any(q in text_lower for q in question_words) and deal.price == 0:
        score = 0.0

    deal.confidence = round(min(score, 1.0), 2)
    return deal
