"""
DonanimHaber forum scraper (Playwright ile) — DÜZELTILMIŞ VERSİYON
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
        self.base_url = base_url
        self.user_agent = user_agent
        self.delay = delay
        self.dh_username = dh_username
        self.dh_password = dh_password
        # Tek browser instance tutacağız
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ──────────────────────────────────────────────
    #  Browser yönetimi (tek instance)
    # ──────────────────────────────────────────────
    def _start_browser(self):
        """Tek bir browser instance başlat."""
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._context = self._browser.new_context(user_agent=self.user_agent)
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins',
                {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages',
                {get: () => ['tr-TR', 'tr', 'en']});
        """)
        self._page = self._context.new_page()

    def _close_browser(self):
        if self._browser:
            self._browser.close()
            self._playwright.stop()
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
                       timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)

            # DH login formu
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

            page.wait_for_timeout(5000)
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
            page.goto(url, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)

            # Login gerekiyorsa (sadece ilk sayfada kontrol et)
            if (page_num == 1 and self.dh_username
                    and page.query_selector("input[type='password']")):
                print("[SCRAPER] Giriş ekranı tespit edildi.")
                if self._login(page):
                    page.goto(url, timeout=60000, wait_until="networkidle")
                    page.wait_for_timeout(5000)

            html = page.content()

            # ── DEBUG: İlk 500 karakteri yazdır ──
            if page_num == 1:
                soup_dbg = BeautifulSoup(html, "lxml")
                txt = soup_dbg.get_text(separator=" ", strip=True)[:500]
                print(f"[DEBUG] Sayfa metni (ilk 500 krk):\n{txt}\n")

            return html

        except Exception as e:
            print(f"[SCRAPER] Fetch error: {e}")
            return None

    # ──────────────────────────────────────────────
    #  ✅ DÜZELTILMIŞ sayfalama URL'si
    # ──────────────────────────────────────────────
    def _get_page_url(self, page: int) -> str:
        """
        DH sayfalama formatı:
          Sayfa 1:  .../konu--132918743
          Sayfa 2:  .../konu--132918743-2
          Sayfa 3:  .../konu--132918743-3
        """
        if page <= 1:
            return self.base_url
        return f"{self.base_url}-{page}"

    # ──────────────────────────────────────────────
    #  Toplam sayfa sayısı
    # ──────────────────────────────────────────────
    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        # DH'de sayfalama linkleri: <a href="...--132918743-21570">21570</a>
        max_page = 1

        # Yöntem 1: Tüm linklerde --ID-SAYFA pattern'i ara
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # --132918743-21570  formatından sayfa numarasını çek
            m = re.search(r"--\d+-(\d+)", href)
            if m:
                max_page = max(max_page, int(m.group(1)))

        # Yöntem 2: "Sayfa: 1 2 3 ... 21570" metninden
        page_text = soup.get_text()
        m = re.search(r"Sayfa.*?(\d[\d.]*)\s*$", page_text, re.M)
        if m:
            try:
                val = int(m.group(1).replace(".", ""))
                max_page = max(max_page, val)
            except ValueError:
                pass

        return max_page

    # ──────────────────────────────────────────────
    #  ✅ DÜZELTILMIŞ post parsing
    # ──────────────────────────────────────────────
    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        # ── DH'nin gerçek yapısına göre mesaj kutucuklarını bul ──
        # Önce bilinen DH selector'larını dene, sonra generic'e düş
        content_els = []

        # DH klasik mesaj yapısı
        dh_selectors = [
            ("div", {"class": re.compile(r"birMesaj|klasikMesaj", re.I)}),
            ("div", {"class": re.compile(r"msgContent|mesajIcerik|mesaj-icerik", re.I)}),
            ("div", {"id": re.compile(r"^msg_\d+")}),
            ("div", {"class": re.compile(r"mesajSatir|mesaj_satir", re.I)}),
            ("div", {"class": re.compile(r"postContent|post-content", re.I)}),
            # IPS fallback (belki bazı sayfalar IPS)
            ("div", {"data-role": "commentContent"}),
            ("div", {"class": re.compile(r"cPost_contentWrap|ipsType_richText", re.I)}),
        ]

        for tag, attrs in dh_selectors:
            found = soup.find_all(tag, attrs=attrs)
            if found:
                content_els = found
                print(f"  [PARSE] Selector eşleşti: <{tag} {attrs}> → {len(found)} adet")
                break

        # Hiçbiri bulamadıysa, debug için sayfayı dump et
        if not content_els:
            print(f"  ⚠️  Sayfa {page}: Hiçbir selector eşleşmedi!")
            print(f"  [DEBUG] Sayfadaki tüm <div> class'ları:")
            all_divs = soup.find_all("div", class_=True)
            seen = set()
            for d in all_divs:
                for c in d.get("class", []):
                    if c not in seen:
                        seen.add(c)
            for c in sorted(seen):
                print(f"    .{c}")

            # Son çare: en uzun metin bloklarını bul
            print("  [DEBUG] En uzun 3 <div> metni:")
            divs_with_text = [(d, len(d.get_text(strip=True)))
                              for d in all_divs if d.get_text(strip=True)]
            divs_with_text.sort(key=lambda x: -x[1])
            for d, length in divs_with_text[:3]:
                print(f"    class={d.get('class')} len={length}")
                print(f"    text={d.get_text(strip=True)[:200]}")
            return posts

        print(f"  Sayfa {page}: {len(content_els)} mesaj bulundu.")

        for el in content_els:
            # Alıntıları temizle
            for quote in el.find_all(["blockquote", "div"],
                                     class_=re.compile(r"quote|Quote|alinan|Alinan", re.I)):
                quote.decompose()

            content = el.get_text(separator=" ", strip=True)
            content = re.sub(r"\s+", " ", content)
            if not content or len(content) < 10:
                continue

            # ── Yazar ve post ID bul ──
            post_id = ""
            author = ""
            timestamp = ""

            # DH: id="msg_123456789"
            parent = el
            for _ in range(5):  # En fazla 5 seviye yukarı
                pid = parent.get("id", "")
                m = re.search(r"msg[_-]?(\d+)", pid, re.I)
                if m:
                    post_id = m.group(1)
                    break
                parent = parent.parent
                if parent is None:
                    break

            # Yazar: DH'de genellikle <a class="nick"> veya <span class="yazar">
            if parent:
                author_el = parent.find(
                    ["a", "span"],
                    class_=re.compile(r"nick|yazar|author|username|kullanici", re.I)
                )
                if author_el:
                    author = author_el.get_text(strip=True)

                # Tarih
                date_el = parent.find(
                    ["span", "a", "time"],
                    class_=re.compile(r"tarih|date|time|mesajTarih", re.I)
                )
                if date_el:
                    timestamp = date_el.get_text(strip=True)

            if not post_id:
                post_id = f"p{page}_{hash(content[:50]) % 100000}"

            posts.append(ForumPost(
                post_id=post_id,
                author=author,
                timestamp=timestamp,
                content=content,
                url=self._get_page_url(page),
                page=page,
            ))

        return posts

    # ──────────────────────────────────────────────
    #  Ana scrape fonksiyonu
    # ──────────────────────────────────────────────
    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        all_posts: List[ForumPost] = []

        try:
            # İlk sayfa
            html = self._fetch_page_html(self.base_url, page_num=1)
            if not html:
                print("[SCRAPER] İlk sayfa yüklenemedi!")
                return all_posts

            soup = BeautifulSoup(html, "lxml")
            total_pages = self._get_total_pages(soup)
            pages_to_scan = min(num_pages, total_pages)
            print(f"Toplam {total_pages} sayfa, {pages_to_scan} sayfa taranacak.")

            all_posts.extend(self._parse_posts(html, 1))

            # Diğer sayfalar (aynı browser ile!)
            for pg in range(2, pages_to_scan + 1):
                time.sleep(self.delay)
                url = self._get_page_url(pg)
                print(f"Sayfa {pg} yükleniyor: {url}")
                html = self._fetch_page_html(url, page_num=pg)
                if html:
                    all_posts.extend(self._parse_posts(html, pg))

        finally:
            self._close_browser()

        print(f"Toplam {len(all_posts)} post bulundu.")
        return all_posts
