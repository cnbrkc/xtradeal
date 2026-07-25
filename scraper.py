"""
DonanimHaber forum scraper — SON SAYFADAN geriye tarar.
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

    # ──────────────────────────────────────────────
    #  Browser yönetimi — TEK instance
    # ──────────────────────────────────────────────
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
        print("[SCRAPER] Browser başlatıldı (headless).")

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

    # ──────────────────────────────────────────────
    #  Login
    # ──────────────────────────────────────────────
    def _login(self, page):
        if not self.dh_username or not self.dh_password:
            return False
        print("[SCRAPER] Forum'a giriş yapılıyor...")
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

    # ──────────────────────────────────────────────
    #  Sayfa HTML'ini çek
    # ──────────────────────────────────────────────
    def _fetch_page_html(self, url: str, page_num: int = 1) -> Optional[str]:
        self._start_browser()
        page = self._page
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(10000)

            if (page_num == 1 and self.dh_username
                    and page.query_selector("input[type='password']")):
                print("[SCRAPER] Giriş ekranı tespit edildi.")
                if self._login(page):
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(10000)

            try:
                page.wait_for_selector(
                    "article.kl-icerik-satir, div.ki-cevapicerigi, span.msg",
                    timeout=20000
                )
            except PlaywrightTimeoutError:
                print("[SCRAPER] ⚠️ Mesaj kutucukları beklenirken zaman aşımı.")

            html = page.content()

            if page_num <= 1:
                soup_dbg = BeautifulSoup(html, "lxml")
                txt = soup_dbg.get_text(separator=" ", strip=True)[:300]
                print(f"[DEBUG] Sayfa metni (ilk 300 krk): {txt}\n")

            return html
        except Exception as e:
            print(f"[SCRAPER] Fetch error: {e}")
            return None

    # ──────────────────────────────────────────────
    #  DH sayfalama URL'si
    # ──────────────────────────────────────────────
    def _get_page_url(self, page: int) -> str:
        if page <= 1:
            return self.base_url
        return f"{self.base_url}-{page}"

    # ──────────────────────────────────────────────
    #  Toplam sayfa sayısı
    # ──────────────────────────────────────────────
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

    # ──────────────────────────────────────────────
    #  Post parsing (DH'ye özel)
    # ──────────────────────────────────────────────
    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        articles = soup.find_all("article", class_="kl-icerik-satir")
        if articles:
            print(f"  Sayfa {page}: {len(articles)} mesaj (article.kl-icerik-satir)")
            for art in articles:
                post = self._parse_article(art, page)
                if post:
                    posts.append(post)
            return posts

        cevap_divs = soup.find_all("div", class_="ki-cevapicerigi")
        if cevap_divs:
            print(f"  Sayfa {page}: {len(cevap_divs)} mesaj (div.ki-cevapicerigi)")
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
            print(f"  Sayfa {page}: {len(msg_spans)} mesaj (span.msg)")
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
        all_els = soup.find_all(class_=True)
        seen = set()
        for el in all_els:
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
        author_aside = art.find("aside", class_="ki-cevapsahibi")
        if author_aside:
            b_el = author_aside.find("b")
            if b_el:
                author = b_el.get_text(strip=True)

        timestamp = ""
        tarih_el = art.find("span", class_="ki-cevaptarihi")
        if tarih_el:
            time_el = tarih_el.find("time")
            timestamp = time_el.get_text(strip=True) if time_el else tarih_el.get_text(strip=True)

        post_id = ""
        art_id = art.get("id", "")
        m = re.search(r"(\d+)", art_id)
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
    #  ✅ YENİ: SON SAYFADAN GERİYE TARAMA
    # ──────────────────────────────────────────────
    def scrape_latest(self, num_pages: int = 5,
                      start_page: int = 0) -> tuple[List[ForumPost], int, int]:
        """
        Son sayfadan geriye doğru tarar.

        Args:
            num_pages:  Kaç sayfa taranacak (son sayfadan geriye)
            start_page: Nereden başlanacak (0 = en son sayfa)

        Returns:
            (posts, last_scanned_page, total_pages)
        """
        all_posts: List[ForumPost] = []

        try:
            # ── 1) Önce son sayfayı aç, toplam sayfa sayısını öğren ──
            if start_page <= 0:
                # Son sayfayı bulmak için önce 1. sayfayı aç
                # (data-maxpage orada)
                print("[SCRAPER] Toplam sayfa sayısı öğreniliyor...")
                html = self._fetch_page_html(self.base_url, page_num=0)
                if not html:
                    print("[SCRAPER] İlk sayfa yüklenemedi!")
                    return all_posts, 0, 0

                soup = BeautifulSoup(html, "lxml")
                total_pages = self._get_total_pages(soup)
                print(f"[SCRAPER] Toplam sayfa: {total_pages}")

                if total_pages <= 1:
                    # Tek sayfalık konu
                    all_posts.extend(self._parse_posts(html, 1))
                    return all_posts, 1, total_pages

                start_page = total_pages
            else:
                # State'den gelen sayfa numarası
                # Yine de toplam sayfayı öğren
                html_tmp = self._fetch_page_html(self.base_url, page_num=0)
                total_pages = 0
                if html_tmp:
                    soup_tmp = BeautifulSoup(html_tmp, "lxml")
                    total_pages = self._get_total_pages(soup_tmp)
                # Eğer konu büyüdüyse (yeni sayfalar eklendiyse)
                if total_pages > start_page:
                    print(f"[SCRAPER] Konu büyümüş! {start_page} → {total_pages}")
                    start_page = total_pages

            # ── 2) Son sayfadan geriye tara ──
            pages_to_scan = min(num_pages, start_page)
            end_page = max(1, start_page - pages_to_scan + 1)

            print(f"[SCRAPER] Sayfa {start_page} → {end_page} arası taranacak "
                  f"({pages_to_scan} sayfa, tersten)")

            last_scanned_page = start_page

            for pg in range(start_page, end_page - 1, -1):
                url = self._get_page_url(pg)
                print(f"  Sayfa {pg} yükleniyor: {url}")
                html = self._fetch_page_html(url, page_num=pg)
                if html:
                    posts = self._parse_posts(html, pg)
                    all_posts.extend(posts)
                    last_scanned_page = pg

                    # İlk post ID'yi yakala (state için)
                    if posts:
                        print(f"  → {len(posts)} post, "
                              f"ilk: {posts[0].post_id}, "
                              f"son: {posts[-1].post_id}")

                time.sleep(self.delay)

        finally:
            self._close_browser()

        print(f"[SCRAPER] Toplam {len(all_posts)} post bulundu "
              f"(sayfa {start_page}→{last_scanned_page}).")
        return all_posts, last_scanned_page, total_pages

    # ──────────────────────────────────────────────
    #  Eski scrape (geriye uyumluluk)
    # ──────────────────────────────────────────────
    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        posts, _, _ = self.scrape_latest(num_pages)
        return posts
