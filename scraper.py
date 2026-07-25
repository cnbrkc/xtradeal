"""
DonanimHaber forum scraper (Playwright ile) — DH'ye özel düzeltilmiş versiyon.
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
        # Tek browser instance
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
            headless=True,  # ✅ GitHub Actions için headless
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
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
            print("[SCRAPER] Browser kapatıldı.")

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
            # ✅ domcontentloaded kullan, networkidle KULLANMA
            # (DH sürekli arka plan isteği atıyor, networkidle hiç tetiklenmez)
            page.goto(url, timeout=60000, wait_until="domcontentloaded")

            # ✅ Sayfanın render olması için explicit bekleme
            page.wait_for_timeout(10000)

            # Login gerekiyorsa (sadece ilk sayfada)
            if (page_num == 1 and self.dh_username
                    and page.query_selector("input[type='password']")):
                print("[SCRAPER] Giriş ekranı tespit edildi.")
                if self._login(page):
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(10000)

            # ✅ DH'nin gerçek mesaj container'ını bekle
            try:
                page.wait_for_selector(
                    "article.kl-icerik-satir, div.ki-cevapicerigi, span.msg",
                    timeout=20000
                )
                print("[SCRAPER] Mesaj kutucukları bulundu!")
            except PlaywrightTimeoutError:
                print("[SCRAPER] ⚠️ Mesaj kutucukları beklenirken zaman aşımı.")
                print("[SCRAPER] Sayfa başlığı:", page.title())

            html = page.content()

            # ── DEBUG: İlk sayfada yapıyı log'a yazdır ──
            if page_num == 1:
                soup_dbg = BeautifulSoup(html, "lxml")
                txt = soup_dbg.get_text(separator=" ", strip=True)[:500]
                print(f"[DEBUG] Sayfa metni (ilk 500 krk):\n{txt}\n")

                # Hangi selector'ların eşleştiğini göster
                for sel_name, sel in [
                    ("article.kl-icerik-satir", "article.kl-icerik-satir"),
                    ("div.ki-cevapicerigi", "div.ki-cevapicerigi"),
                    ("span.msg", "span.msg"),
                    ("aside.ki-cevapsahibi", "aside.ki-cevapsahibi"),
                ]:
                    try:
                        cnt = page.locator(sel).count()
                        print(f"[DEBUG] {sel_name} → {cnt} adet")
                    except:
                        print(f"[DEBUG] {sel_name} → hata")

            return html

        except Exception as e:
            print(f"[SCRAPER] Fetch error: {e}")
            return None

    # ──────────────────────────────────────────────
    #  ✅ DH sayfalama URL'si
    # ──────────────────────────────────────────────
    def _get_page_url(self, page: int) -> str:
        """
        DH sayfalama: URL sonuna -N eklenir
          Sayfa 1:  .../konu--132918743
          Sayfa 2:  .../konu--132918743-2
        """
        if page <= 1:
            return self.base_url
        return f"{self.base_url}-{page}"

    # ──────────────────────────────────────────────
    #  ✅ Toplam sayfa sayısı (data-maxpage)
    # ──────────────────────────────────────────────
    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        # Yöntem 1: data-maxpage attribute (en güvenilir)
        el = soup.find(attrs={"data-maxpage": True})
        if el:
            try:
                return int(el["data-maxpage"])
            except (ValueError, TypeError):
                pass

        # Yöntem 2: Sayfalama linklerinden --ID-SAYFA pattern'i
        max_page = 1
        for a in soup.find_all("a", href=True):
            m = re.search(r"--\d+-(\d+)", a["href"])
            if m:
                max_page = max(max_page, int(m.group(1)))

        # Yöntem 3: "Sayfa: 1 2 3 ... 21.570" metninden
        page_text = soup.get_text()
        m = re.search(r"Sayfa.*?([\d.]+)\s*$", page_text, re.M)
        if m:
            try:
                val = int(m.group(1).replace(".", ""))
                max_page = max(max_page, val)
            except ValueError:
                pass

        return max_page

    # ──────────────────────────────────────────────
    #  ✅ DH'ye özel post parsing
    # ──────────────────────────────────────────────
    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        # ── DH'nin gerçek yapısına göre mesajları bul ──
        # Öncelik: article.kl-icerik-satir (yeni DH)
        articles = soup.find_all("article", class_="kl-icerik-satir")

        if articles:
            print(f"  Sayfa {page}: {len(articles)} mesaj bulundu (article.kl-icerik-satir).")
            for art in articles:
                post = self._parse_article(art, page)
                if post:
                    posts.append(post)
            return posts

        # Fallback 1: div.ki-cevapicerigi (eski DH)
        cevap_divs = soup.find_all("div", class_="ki-cevapicerigi")
        if cevap_divs:
            print(f"  Sayfa {page}: {len(cevap_divs)} mesaj bulundu (div.ki-cevapicerigi).")
            for div in cevap_divs:
                post = self._parse_cevap_div(div, page)
                if post:
                    posts.append(post)
            return posts

        # Fallback 2: span.msg (en generic)
        msg_spans = soup.find_all("span", class_="msg")
        if msg_spans:
            print(f"  Sayfa {page}: {len(msg_spans)} mesaj bulundu (span.msg).")
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

        # Hiçbiri bulamadı → DEBUG dump
        print(f"  ⚠️ Sayfa {page}: Hiçbir DH selector'ı eşleşmedi!")
        print(f"  [DEBUG] Sayfadaki tüm class'lar:")
        all_els = soup.find_all(class_=True)
        seen = set()
        for el in all_els:
            for c in el.get("class", []):
                if c not in seen:
                    seen.add(c)
        for c in sorted(seen):
            print(f"    .{c}")

        # En uzun metin bloklarını göster
        print("  [DEBUG] En uzun 3 <div> metni:")
        divs = [(d, len(d.get_text(strip=True)))
                for d in soup.find_all("div") if d.get_text(strip=True)]
        divs.sort(key=lambda x: -x[1])
        for d, length in divs[:3]:
            print(f"    class={d.get('class')} len={length}")
            print(f"    text={d.get_text(strip=True)[:200]}")

        return posts

    def _parse_article(self, art, page: int) -> Optional[ForumPost]:
        """article.kl-icerik-satir içindeki bir mesajı parse et."""
        # Mesaj içeriği: span.msg
        msg_el = art.find("span", class_="msg")
        if not msg_el:
            return None

        # Alıntıları temizle
        for quote in msg_el.find_all(
            ["blockquote", "div"],
            class_=re.compile(r"quote|Quote|alinan|Alinan|ipsQuote", re.I)
        ):
            quote.decompose()

        content = msg_el.get_text(separator=" ", strip=True)
        content = re.sub(r"\s+", " ", content)
        if not content or len(content) < 10:
            return None

        # Yazar: aside.ki-cevapsahibi > div > a > b
        author = ""
        author_aside = art.find("aside", class_="ki-cevapsahibi")
        if author_aside:
            b_el = author_aside.find("b")
            if b_el:
                author = b_el.get_text(strip=True)
            else:
                a_el = author_aside.find("a")
                if a_el:
                    author = a_el.get_text(strip=True)

        # Tarih: span.ki-cevaptarihi > span > a > time
        timestamp = ""
        tarih_el = art.find("span", class_="ki-cevaptarihi")
        if tarih_el:
            time_el = tarih_el.find("time")
            if time_el:
                timestamp = time_el.get_text(strip=True)
            else:
                timestamp = tarih_el.get_text(strip=True)

        # Post ID: article id'sinden veya data attribute'dan
        post_id = ""
        art_id = art.get("id", "")
        m = re.search(r"(\d+)", art_id)
        if m:
            post_id = m.group(1)
        if not post_id:
            data_pid = art.get("data-postid", "") or art.get("data-id", "")
            if data_pid:
                post_id = data_pid
        if not post_id:
            post_id = f"p{page}_{hash(content[:50]) % 100000}"

        return ForumPost(
            post_id=post_id,
            author=author,
            timestamp=timestamp,
            content=content,
            url=self._get_page_url(page),
            page=page,
        )

    def _parse_cevap_div(self, div, page: int) -> Optional[ForumPost]:
        """div.ki-cevapicerigi (eski DH) parse et."""
        content = div.get_text(separator=" ", strip=True)
        content = re.sub(r"\s+", " ", content)
        if not content or len(content) < 10:
            return None

        author = ""
        author_el = div.find("span", class_="mButon info")
        if author_el:
            author = author_el.get_text(strip=True)

        return ForumPost(
            post_id=f"p{page}_{hash(content[:50]) % 100000}",
            author=author, timestamp="", content=content,
            url=self._get_page_url(page), page=page,
        )

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

            # Diğer sayfalar — AYNI browser ile
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
