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
        if cevap_divs:
            print(f"  Sayfa {page}: {len(cevap_divs)} mesaj (eski DH).")
            for div in cevap_divs:
                content = div.get_text(separator=" ", strip=True)
                content = re.sub(r"\s+", " ", content)
                if content and len(content) > 10:
                    posts.append(ForumPost(
                        post_id=f"p{page}_{hash(content[:50]) % 100000}",
                        author="", timestamp="", content=content,
                        url=self._get_page_url(page), page=page,
                    ))
            return posts

        msg_spans = soup.find_all("span", class_="msg")
        if msg_spans:
            print(f"  Sayfa {page}: {len(msg_spans)} mesaj (span.msg).")
            for sp in msg_spans:
                content = sp.get_text(separator=" ", strip=True)
                content = re.sub(r"\s+", " ", content)
                if content and len(content) > 10:
                    posts.append(ForumPost(
                        post_id=f"p{page}_{hash(content[:50]) % 100000}",
                        author="", timestamp="", content=content,
                        url=self._get_page_url(page), page=page,
                    ))
            return posts

        print(f"  ⚠️ Sayfa {page}: Selector eşleşmedi!")
        seen = set()
        for el in soup.find_all(class_=True):
            for c in el.get("class", []):
                seen.add(c)
        print(f"  [DEBUG] Class'lar: {sorted(seen)[:30]}")
        return posts

    def _parse_article(self, art, page: int) -> Optional[ForumPost]:
        msg_el = art.find("span", class_="msg")
        if not msg_el:
            return None
        for quote in msg_el.find_all(
            ["blockquote", "div"],
            class_=re.compile(r"quote|Quote|alinan|Alinan", re.I)
        ):
            quote.decompose()
        content = msg_el.get_text(separator=" ", strip=True)
        content = re.sub(r"\s+", " ", content)
        if not content or len(content) < 10:
            return None

        author = ""
        aside = art.find("aside", class_="ki-cevapsahibi")
        if aside:
            b = aside.find("b")
            if b:
                author = b.get_text(strip=True)

        timestamp = ""
        tarih = art.find("span", class_="ki-cevaptarihi")
        if tarih:
            t = tarih.find("time")
            timestamp = t.get_text(strip=True) if t else tarih.get_text(strip=True)

        post_id = ""
        m = re.search(r"(\d+)", art.get("id", ""))
        if m:
            post_id = m.group(1)
        if not post_id:
            post_id = art.get("data-postid", "") or art.get("data-id", "")
        if not post_id:
            post_id = f"p{page}_{hash(content[:50]) % 100000}"

        return ForumPost(
            post_id=post_id, author=author, timestamp=timestamp,
            content=content, url=self._get_page_url(page), page=page,
        )

    # ──────────────────────────────────────────────
    #  ✅ YENİ MANTIK: KALDIĞI YERDEN İLERİYE TARA
    # ──────────────────────────────────────────────
    def scrape_latest(self, num_pages: int = 5,
                      last_page: int = 0) -> tuple:
        """
        Kaldığı yerden İLERİYE doğru tarar.

        İlk çalışma (last_page=0):
            Son sayfayı bulur, son N sayfayı tarar.
            21568 → 21569 → 21570 → 21571 → 21572

        Sonraki çalışma (last_page=21572):
            Son sayfayı kontrol eder.
            - Hâlâ 21572 → sadece 21572'yi tara (yeni postlar)
            - 21573 olmuş → 21572 → 21573 tara (ileri)
            - 21575 olmuş → 21572 → 21573 → 21574 → 21575 tara

        Returns:
            (posts, new_last_page, total_pages, last_post_id)
        """
        all_posts: List[ForumPost] = []
        total_pages = 0

        try:
            # ── 1) Son sayfayı aç, total_pages'i öğren ──
            print("[SCRAPER] Son sayfa kontrol ediliyor...")
            # Önce 1. sayfayı açarak total_pages'i bul
            html = self._fetch_page_html(self.base_url, page_num=1)
            if not html:
                print("[SCRAPER] İlk sayfa yüklenemedi!")
                return all_posts, last_page, 0, ""

            soup = BeautifulSoup(html, "lxml")
            total_pages = self._get_total_pages(soup)
            print(f"[SCRAPER] Toplam sayfa: {total_pages}")

            # ── 2) Başlangıç sayfasını belirle ──
            if last_page <= 0:
                # İLK ÇALIŞMA: son N sayfadan başla
                start = max(1, total_pages - num_pages + 1)
                print(f"[SCRAPER] İlk çalışma. "
                      f"Sayfa {start} → {total_pages} taranacak.")
            else:
                # SONRAKİ ÇALIŞMA: kaldığın yerden başla
                start = last_page
                # Eğer konu küçülmüşse (nadir)
                if start > total_pages:
                    start = total_pages
                print(f"[SCRAPER] Kaldığın yerden devam. "
                      f"Sayfa {start} → {total_pages} taranacak.")

            # ── 3) İLERİ DOĞRU tara ──
            pages_scanned = 0
            for pg in range(start, total_pages + 1):
                url = self._get_page_url(pg)
                print(f"\n  📄 Sayfa {pg}/{total_pages}: {url}")
                html = self._fetch_page_html(url, page_num=pg)
                if html:
                    posts = self._parse_posts(html, pg)
                    all_posts.extend(posts)
                    pages_scanned += 1

                    if posts:
                        print(f"     → {len(posts)} post | "
                              f"ilk: {posts[0].post_id} | "
                              f"son: {posts[-1].post_id}")
                time.sleep(self.delay)

            # ── 4) Son post ID'yi belirle ──
            last_post_id = ""
            if all_posts:
                last_post_id = all_posts[-1].post_id

            print(f"\n[SCRAPER] Tarama bitti: "
                  f"{pages_scanned} sayfa, "
                  f"{len(all_posts)} post, "
                  f"son sayfa: {total_pages}, "
                  f"son post: {last_post_id}")

        finally:
            self._close_browser()

        return all_posts, total_pages, total_pages, last_post_id

    # Geriye uyumluluk
    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        posts, _, _, _ = self.scrape_latest(num_pages)
        return posts
