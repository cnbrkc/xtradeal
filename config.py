import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    FORUM_URL: str = os.getenv(
        "FORUM_URL",
        "https://forum.donanimhaber.com/sifir-arac-ve-arac-fiyati-teklifi-alanlar-2022--132918743",
    )
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    SCAN_PAGES: int = int(os.getenv("SCAN_PAGES", "5"))
    DB_PATH: str = os.getenv("DB_PATH", "data/deals.db")
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "2.0"))
    MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.3"))
    
    # DH Giriş Bilgileri
    DH_USERNAME: str = os.getenv("DH_USERNAME", "")
    DH_PASSWORD: str = os.getenv("DH_PASSWORD", "")
    
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
