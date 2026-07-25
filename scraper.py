"""
DonanimHaber forum scraper (Playwright ile giriş yapar).
"""
import re
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin
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
    def __init__(self, base_url: str, user_agent: str, delay: float = 2.0, dh_username: str = "", dh_password: str = ""):
        self.base_url = base_url
        self.user_agent = user_agent
        self.delay = delay
        self.dh_username = dh_username
        self.dh_password = dh_password

    def _login(self, page):
        if not self.dh_username or not self.dh_password:
            print("[SCRAPER] DH kullanıcı adı/şifre bulunamadı, giriş yapılamadı!")
            return False
            
        print("[SCRAPER] Forum'a giriş yapılıyor...")
        try:
            # Giriş sayfasına git
            page.goto("https://forum.donanimhaber.com/login/", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000) # Cloudflare geçerse diye bekle
            
            # Kullanıcı adı ve şifreyi doldur
            page.fill("input[name='auth']", self.dh_username)
            page.fill("input[name='password']", self.dh_password)
            
            # "Bağlan" butonuna tıkla
            page.click("#elSignInSubmit")
            
            # Girişin tamamlanması için bekle
            page.wait_for_timeout(5000)
            print("[SCRAPER] Giriş işlemi tamamlandı.")
            return True
        except Exception as e:
            print(f"[SCRAPER] Giriş hatası: {e}")
            return False

    def _fetch_page_html(self, url: str) -> Optional[str]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=self.user_agent)
            
            # Cloudflare kandırmacası
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en']});
            """)
            
            page = context.new_page()
            
            try:
                # Sayfaya git
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                
                # Eğer sayfada "Üye Girişi" yazıyorsa, giriş yapmamız lazım
                if "Üye Girişi" in page.title() or "Bağlan" in page.content():
                    self._login(page)
                    # Giriş yaptıktan sonra asıl konuya tekrar dön
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                
                title = page.title()
                print(f"[SCRAPER] Açılan Sayfa Başlığı: {title}")

                # Post elementinin yüklenmesini bekle
                try:
                    page.wait_for_selector("article[id^='elComment_'], div[data-postid]", timeout=15000)
                except PlaywrightTimeoutError:
                    pass
                
                html = page.content()
                return html
            except Exception as e:
                print(f"[SCRAPER] Fetch error {url}: {e}")
                return None
            finally:
                browser.close()

    def _get_page_url(self, page: int) -> str:
        if page <= 1:
            return self.base_url
        sep = "&" if "?" in self.base_url else "?"
        return f"{self.base_url}{sep}page={page}"

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        pag = soup.find("ul", class_=re.compile(r"pagination", re.I))
        if not pag:
            pag = soup.find("div", class_=re.compile(r"pagination", re.I))
        if pag:
            links = pag.find_all("a", href=True)
            max_page = 1
            for link in links:
                href = link.get("href", "")
                m = re.search(r"page=(\d+)", href)
                if m:
                    max_page = max(max_page, int(m.group(1)))
                dp = link.get("data-page")
                if dp:
                    max_page = max(max_page, int(dp))
            return max_page
        return 1

    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        articles = soup.find_all("article", id=re.compile(r"elComment_\d+"))
        if not articles:
            articles = soup.find_all(attrs={"data-postid": True})
        if not articles:
            articles = soup.find_all("div", class_=re.compile(r"cPost|ipsComment"))

        if not articles:
            print(f"[SCRAPER] Sayfa {page}: post bulunamadı! Giriş başarısız olabilir.")
            return posts

        for article in articles:
            post_id = ""
            pid = article.get("id", "")
            m = re.search(r"\d+", pid)
            if m:
                post_id = m.group()
            elif article.get("data-postid"):
                post_id = article.get("data-postid")
            if not post_id:
                continue

            author = ""
            author_el = article.find("a", class_=re.compile(r"ipsType_break|author|username", re.I))
            if not author_el:
                aside = article.find("aside")
                if aside:
                    author_el = aside.find("a", href=True)
            if author_el:
                author = author_el.get_text(strip=True)

            timestamp = ""
            time_el = article.find("time")
            if time_el:
                timestamp = time_el.get("datetime", "") or time_el.get("title", "") or time_el.get_text(strip=True)

            content = ""
            content_el = article.find("div", class_=re.compile(r"cPost_contentWrap|ipsType_normal|post_content|ipsComment_content", re.I))
            if not content_el:
                content_el = article.find("div", class_=re.compile(r"post_message|messageContent", re.I))
            if content_el:
                for quote in content_el.find_all(["blockquote", "div"], class_=re.compile(r"ipsQuote|quote", re.I)):
                    quote.decompose()
                for edit in content_el.find_all(attrs={"class": re.compile(r"ipsEdit|edit", re.I)}):
                    edit.decompose()
                content = content_el.get_text(separator=" ", strip=True)
                content = re.sub(r"\s+", " ", content)

            post_url = ""
            share_el = article.find("a", class_=re.compile(r"ipsType_blendLinks|share|permalink", re.I))
            if share_el:
                post_url = share_el.get("href", "")
            if post_url and not post_url.startswith("http"):
                post_url = urljoin(self.base_url, post_url)

            posts.append(
                ForumPost(
                    post_id=post_id, author=author, timestamp=timestamp,
                    content=content, url=post_url, page=page,
                )
            )
        return posts

    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        all_posts: List[ForumPost] = []

        html = self._fetch_page_html(self.base_url)
        if not html:
            print("[SCRAPER] İlk sayfa yüklenemedi!")
            return all_posts

        soup = BeautifulSoup(html, "lxml")
        total_pages = self._get_total_pages(soup)
        pages_to_scan = min(num_pages, total_pages)
        print(f"[SCRAPER] Toplam {total_pages} sayfa, {pages_to_scan} sayfa taranacak.")

        all_posts.extend(self._parse_posts(html, 1))

        for page in range(2, pages_to_scan + 1):
            time.sleep(self.delay)
            url = self._get_page_url(page)
            print(f"[SCRAPER] Sayfa {page} yükleniyor: {url}")
            html = self._fetch_page_html(url)
            if html:
                all_posts.extend(self._parse_posts(html, page))

        print(f"[SCRAPER] Toplam {len(all_posts)} post bulundu.")
        return all_posts
