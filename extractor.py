"""
Forum post metninden araç bilgisi, fiyat, bayi adı çıkarır.
Türkçe sayı formatlarını ve araç marka/model isimlerini tanır.
"""
import re
from dataclasses import dataclass
from typing import Optional

# ──────────────────────────────────────────────────────────────────── #
#  Araç marka ve model veritabanı                                     #
# ──────────────────────────────────────────────────────────────────── #

CAR_BRANDS = [
    "Volkswagen", "Audi", "BMW", "Mercedes-Benz", "Mercedes", "Toyota", "Honda",
    "Hyundai", "Kia", "Nissan", "Mazda", "Skoda", "Seat", "Peugeot", "Renault",
    "Citroen", "Citroën", "Fiat", "Ford", "Opel", "Volvo", "Dacia", "Mitsubishi",
    "Suzuki", "Lexus", "Porsche", "Alfa Romeo", "Subaru", "Land Rover", "Jaguar",
    "Mini", "Cooper", "Tesla", "Cupra", "Togg", "Chery", "MG", "BYD", "Nio",
    "Tofaş", "Anadol", "DS", "Jeep", "SsangYong", "Infiniti", "Genesis",
]

CAR_MODELS = {
    "Volkswagen": ["Passat", "Golf", "Polo", "Tiguan", "T-Roc", "Arteon",
                   "Touareg", "Caddy", "Touran", "Taigo", "Jetta", "Scirocco",
                   "Beetle", "ID.4", "ID.3", "ID.5", "ID.7", "T-Cross"],
    "Audi": ["A3", "A4", "A5", "A6", "A7", "A8", "Q2", "Q3", "Q4", "Q5",
             "Q7", "Q8", "e-tron", "TT", "RS3", "RS4", "RS5", "RS6", "S3", "S4"],
    "BMW": ["1 Serisi", "2 Serisi", "3 Serisi", "4 Serisi", "5 Serisi",
            "6 Serisi", "7 Serisi", "X1", "X2", "X3", "X4", "X5", "X6", "X7",
            "i4", "iX", "iX3", "320i", "330i", "520i", "530i", "118i", "120i",
            "320d", "330d", "520d", "M3", "M4", "M5"],
    "Mercedes": ["A Serisi", "C Serisi", "E Serisi", "S Serisi", "GLA", "GLB",
                 "GLC", "GLE", "GLS", "CLA", "CLC", "GLK", "A180", "A200",
                 "C180", "C200", "C220", "C300", "E200", "E300", "E350",
                 "AMG", "EQS", "EQA", "EQB", "EQE", "EQC"],
    "Toyota": ["Corolla", "Yaris", "C-HR", "CHR", "RAV4", "Camry", "Hilux",
               "Land Cruiser", "Auris", "Avensis", "Prius", "Corolla Cross",
               "Yaris Cross", "Proace", "GT86", "GR86", "Supra"],
    "Honda": ["Civic", "City", "CR-V", "CRV", "HR-V", "HRV", "Jazz",
              "Accord", "HRV e:HEV", "Civic Type-R"],
    "Hyundai": ["i20", "i30", "Tucson", "Santa Fe", "Elantra", "Accent",
                "Bayon", "Kona", "Sonata", "Staria", "i10", "Staria",
                "IONIQ", "Ioniq 5", "Ioniq 6", "Venue"],
    "Kia": ["Cerato", "Ceed", "Sportage", "Sorento", "Picanto", "Rio",
            "Stonic", "Seltos", "Niro", "EV6", "Stinger", "Carens",
            "Carnival", "Soul", "Xceed", "Proceed"],
    "Nissan": ["Qashqai", "Juke", "X-Trail", "Micra", "Leaf", "Patrol",
               "Navara", "Ariya", "Magnite"],
    "Mazda": ["CX-3", "CX-5", "CX-30", "CX-50", "CX-60", "Mazda3", "Mazda6",
              "MX-5", "MX-30"],
    "Skoda": ["Octavia", "Superb", "Scala", "Kamiq", "Karoq", "Kodiaq",
              "Fabia", "Enyaq", "Slavia"],
    "Seat": ["Leon", "Ibiza", "Ateca", "Arona", "Toledo", "Tarraco"],
    "Cupra": ["Formentor", "Leon", "Ateca", "Born"],
    "Peugeot": ["208", "308", "3008", "5008", "2008", "Partner", "Rifter",
                "408", "508", "Expert", "Traveller", "e-208", "e-308"],
    "Renault": ["Clio", "Megane", "Captur", "Kadjar", "Talisman", "Symbol",
                "Duster", "Kangoo", "Arkana", "Austral", "Espace", "Twingo",
                "Zoe", "Taliant", "Toros"],
    "Dacia": ["Duster", "Sandero", "Logan", "Jogger", "Spring", "Dokker"],
    "Citroen": ["C3", "C4", "C5", "C-Elysee", "Berlingo", "C3 Aircross",
                "C4 Cactus", "Spacetourer"],
    "Citroën": ["C3", "C4", "C5", "C-Elysee", "Berlingo", "C3 Aircross",
                "C4 Cactus", "Spacetourer"],
    "Fiat": ["Egea", "500", "Panda", "Doblo", "500X", "500L", "Tipo",
             "Ducato", "Fiorino", "Punto", "Grande Punto", "124 Spider",
             "500e"],
    "Ford": ["Focus", "Fiesta", "Puma", "Kuga", "EcoSport", "Mondeo",
             "Courier", "Transit", "Mustang", "Bronco", "Ranger", "Edge",
             "Tourneo", "Puma Gen-E"],
    "Opel": ["Astra", "Corsa", "Mokka", "Grandland", "Insignia", "Crossland",
             "Combo", "Vivaro", "Zafira"],
    "Volvo": ["XC40", "XC60", "XC90", "S60", "V40", "V60", "V90", "C40",
              "EX30", "EX90", "S90"],
    "Togg": ["T10X", "T10F", "T8X", "Sedan"],
}

# Marka normalization
BRAND_NORMALIZE = {
    "mercedes-benz": "Mercedes",
    "cooper": "Mini",
    "citroën": "Citroen",
}

# Motor/types after brand+model for extra context
ENGINE_PATTERNS = [
    r"\b\d\.\d\s*(?:TDI|TFSI|TSI|DSG|D-4D|VTEC|MPI|CRDi|GTDi|eTSI|Hybrid|mHEV|BlueHDi|dCi|TCE|THP|PureTech|SkyActiv|i-MMD|eHDi|CDTi)\b",
    r"\b\d\.\d\s*(?:D|DCT|AMT|MT|AT)\b",
    r"\b(?:Hybrid|Plug-in|mHEV|PHEV|BEV)\b",
]

BRAND_RE = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in sorted(CAR_BRANDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────── #
#  Data class                                                         #
# ──────────────────────────────────────────────────────────────────── #

@dataclass
class CarDeal:
    post_id: str
    author: str
    timestamp: str
    content: str
    url: str
    page: int
    car_brand: Optional[str] = None
    car_model: Optional[str] = None
    price: Optional[int] = None
    price_text: Optional[str] = None
    dealer: Optional[str] = None
    year: Optional[str] = None
    confidence: float = 0.0


# ──────────────────────────────────────────────────────────────────── #
#  Extractors                                                         #
# ──────────────────────────────────────────────────────────────────── #

def extract_price(text: str) -> tuple[Optional[int], Optional[str]]:
    """Türkçe formatlardan fiyat çıkar.
    Desteklenen formatlar:
      1.250.000 TL, 1.250.000₺, 1.250.000 ₺
      1250 bin, 1.250 bin
      1.25 milyon, 1,25 milyon
    """
    # 1) Tam fiyat: 1.250.000 TL / ₺
    m = re.search(r"(\d{1,3}(?:\.\d{3})+)\s*(?:TL|₺|TRY|tl|₺)", text, re.I)
    if m:
        raw = m.group(1)
        price = int(raw.replace(".", ""))
        if price >= 50000:
            return price, f"{raw} TL"

    # 2) 1.250.000 (en az 6 hane, context'te TL/₺ olmasa da)
    m = re.search(r"(\d{1,3}(?:\.\d{3}){1,})", text)
    if m:
        raw = m.group(1)
        price = int(raw.replace(".", ""))
        if price >= 500000:
            return price, f"{raw} TL"

    # 3) "1250 bin" / "1.250 bin"
    m = re.search(r"(\d{1,4}(?:\.\d{3})*)\s*bin\s*(?:TL|₺)?", text, re.I)
    if m:
        num_str = m.group(1).replace(".", "")
        try:
            price = int(num_str) * 1000
            if price >= 50000:
                return price, m.group(0).strip()
        except ValueError:
            pass

    # 4) "1.25 milyon" / "1,25 milyon"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*milyon\s*(?:TL|₺)?", text, re.I)
    if m:
        num_str = m.group(1).replace(",", ".")
        try:
            price = int(float(num_str) * 1_000_000)
            if price >= 100000:
                return price, m.group(0).strip()
        except ValueError:
            pass

    return None, None


def extract_car_info(text: str) -> tuple[Optional[str], Optional[str]]:
    """Araç markası ve modelini çıkar."""

    m = BRAND_RE.search(text)
    if not m:
        return None, None

    raw_brand = m.group(1)
    brand_key = raw_brand.lower()
    brand = BRAND_NORMALIZE.get(brand_key, raw_brand.title())

    # Model eşleştir
    models = CAR_MODELS.get(brand, [])
    model = None

    # Markadan sonraki 60 karakterde model ara
    text_after = text[m.end():m.end() + 80]

    for mdl in models:
        # Model isminde özel karakterler varsa escape et
        pat = re.compile(re.escape(mdl), re.I)
        if pat.search(text_after) or pat.search(text[m.end():m.end() + 200]):
            model = mdl
            break

    # Motor tipi yakala (model bulunamadıysa)
    if not model:
        for ep in ENGINE_PATTERNS:
            em = re.search(ep, text, re.I)
            if em:
                model = em.group(0).strip()
                break

    # Trim seviyesi yakala (Comfort, Dream, Elite, vs.)
    trim_match = re.search(
        r"\b(Comfort|Dream|Elite|Premium|Style|Life|Hatchback|Sedan|Wagon|"
        r"ATT|BMT|MHEV|DCT|Plus|Pro|Executive|Launch|Icon|Elite Plus|"
        r"Peugeot|Allure|Active|Allure|GT Line|GT)\b",
        text[m.end():m.end() + 200],
        re.I,
    )
    if trim_match and model:
        model = f"{model} {trim_match.group(1)}"

    return brand, model


def extract_dealer(text: str) -> Optional[str]:
    """Bayi / galeri adını çıkar."""

    patterns = [
        # "Bayi: X" / "Bayi X"
        r"[Bb]ayi[:\s]+([A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]+?)(?:\n|$|,|;|\.|!|\?|Fiyat|fiyat)",
        # "X Otomotiv"
        r"([A-ZÇĞİÖŞÜ][A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]{2,30})\s+[Oo]tomotiv",
        # "X Galeri"
        r"([A-ZÇĞİÖŞÜ][A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]{2,30})\s+[Gg]aleri",
        # "X Bayisi" / "X Bayi"
        r"([A-ZÇĞİÖŞÜ][A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]{2,30})\s+[Bb]ayi",
        # "Diler: X"
        r"[Dd]iler[:\s]+([A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]+?)(?:\n|$|,|;|\.|!|\?)",
        # "X A.Ş." / "X AŞ"
        r"([A-ZÇĞİÖŞÜ][A-Za-zÇĞİıÖŞÜçğıöşü0-9\s.&-]{2,30})\s+A\.?Ş\.?",
    ]

    for pat in patterns:
        m = re.search(pat, text)
        if m:
            dealer = m.group(1).strip()
            # Çok kısa veya çok uzunsa atla
            if 2 < len(dealer) < 50:
                # Marka adıyla aynı değilse
                if dealer.lower() not in [b.lower() for b in CAR_BRANDS]:
                    return dealer

    return None


def extract_year(text: str) -> Optional[str]:
    """Araç model yılını çıkar."""
    # "2023 model", "2023", "23 model"
    m = re.search(r"\b(20[12]\d)\s*(?:model|yıl| Yıl)?\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b('2[0-9])\s*model\b", text)
    if m:
        return f"20{m.group(1)[1:]}"
    return None


# ──────────────────────────────────────────────────────────────────── #
#  Main extraction function                                           #
# ──────────────────────────────────────────────────────────────────── #

def extract_deal(post) -> CarDeal:
    """Bir ForumPost'tan CarDeal üret."""

    brand, model = extract_car_info(post.content)
    price, price_text = extract_price(post.content)
    dealer = extract_dealer(post.content)
    year = extract_year(post.content)

    # Güven skoru
    confidence = 0.0
    if brand:
        confidence += 0.3
    if model:
        confidence += 0.2
    if price:
        confidence += 0.3
    if dealer:
        confidence += 0.1
    if year:
        confidence += 0.1

    return CarDeal(
        post_id=post.post_id,
        author=post.author,
        timestamp=post.timestamp,
        content=post.content[:500],
        url=post.url,
        page=post.page,
        car_brand=brand,
        car_model=model,
        price=price,
        price_text=price_text,
        dealer=dealer,
        year=year,
        confidence=confidence,
    )
