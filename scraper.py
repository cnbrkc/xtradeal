"""
DonanimHaber forum scraper — KALDIĞI YERDEN İLERİYE tarar.
"""

import re
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


@dataclass
class ForumPost:
    post_id: str
    author: str
    timestamp: str
    content: str
    url: str
    page: int


class DonanimHaberScraper:

    def __init__(self, base_url: str, user_agent: str, delay: float = 2.0,
                 dh_username: str = "", dh_password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.delay = delay
        self.dh_username = dh_username
        self.dh_password = dh_password
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ── Browser ──
    def _start_browser(self):
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"]
        )
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="tr-TR",
        )
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins',
                {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages',
                {get: () => ['tr-TR', 'tr', 'en']});
        """)
        self._page = self._context.new_page()
        print("[SCRAPER] Browser başlatıldı.")

    def _close_browser(self):
        if self._browser:
            try:
                self._browser.close()
            except:
                pass
            try:
                self._playwright.stop()
            except:
                pass
            self._browser = None
            self._page = None

    # ── Login ──
    def _login(self, page):
        if not self.dh_username or not self.dh_password:
            return False
        print("[SCRAPER] Giriş yapılıyor...")
        try:
            page.goto("https://forum.donanimhaber.com/login/",
                       timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            page.wait_for_selector("input[type='password']", timeout=15000)
            page.locator("input[type='password']").first.fill(self.dh_password)
            for sel in ["input[name='auth']", "input[name='username']",
                        "input[type='email']", "input[type='text']"]:
                try:
                    if page.locator(sel).first.is_visible():
                        page.locator(sel).first.fill(self.dh_username)
                        break
                except:
                    continue
            for sel in ["#elSignInSubmit", "button[type='submit']",
                        "input[type='submit']"]:
                try:
                    if page.locator(sel).first.is_visible():
                        page.locator(sel).first.click()
                        break
                except:
                    continue
            page.wait_for_timeout(8000)
            print("[SCRAPER] Giriş tamamlandı.")
            return True
        except Exception as e:
            print(f"[SCRAPER] Giriş hatası: {e}")
            return False

    # ── Sayfa çek ──
    def _fetch_page_html(self, url: str, page_num: int = 1) -> Optional[str]:
        self._start_browser()
        page = self._page
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(10000)

            if (page_num == 1 and self.dh_username
                    and page.query_selector("input[type='password']")):
                if self._login(page):
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(10000)

            try:
                page.wait_for_selector(
                    "article.kl-icerik-satir, div.ki-cevapicerigi, span.msg",
                    timeout=20000
                )
            except PlaywrightTimeoutError:
                print("[SCRAPER] ⚠️ Mesaj kutucukları zaman aşımı.")

            return page.content()
        except Exception as e:
            print(f"[SCRAPER] Fetch error: {e}")
            return None

    # ── DH sayfalama URL ──
    def _get_page_url(self, page: int) -> str:
        if page <= 1:
            return self.base_url
        return f"{self.base_url}-{page}"

    # ── Toplam sayfa ──
    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        el = soup.find(attrs={"data-maxpage": True})
        if el:
            try:
                return int(el["data-maxpage"])
            except (ValueError, TypeError):
                pass
        max_page = 1
        for a in soup.find_all("a", href=True):
            m = re.search(r"--\d+-(\d+)", a["href"])
            if m:
                max_page = max(max_page, int(m.group(1)))
        return max_page

    # ── Post parsing ──
    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        articles = soup.find_all("article", class_="kl-icerik-satir")
        if articles:
            print(f"  Sayfa {page}: {len(articles)} mesaj bulundu.")
            for art in articles:
                post = self._parse_article(art, page)
                if post:
                    posts.append(post)
            return posts

        cevap_divs = soup.find_all("div", class_="ki-cevapicerigi")
       
