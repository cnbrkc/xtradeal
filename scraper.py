"""
DonanimHaber forum scraper (Playwright ile).
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
            return False
            
        print("[SCRAPER] Forum'a giriş yapılıyor...")
        try:
            page.goto("https://forum.donanimhaber.com/login/", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            page.wait_for_selector("input[type='password']", timeout=15000)
            page.locator("input[type='password']").first.fill(self.dh_password)
            
            username_selectors = ["input[name='auth']", "input[name='username']", "input[type='email']", "input[type='text']"]
            for sel in username_selectors:
                try:
                    if page.locator(sel).first.is_visible():
                        page.locator(sel).first.fill(self.dh_username)
                        break
                except:
                    continue
            
            submit_selectors = ["#elSignInSubmit", "button[type='submit']", "input[type='submit']"]
            for sel in submit_selectors:
                try:
                    if page.locator(sel).first.is_visible():
                        page.locator(sel).first.click()
                        break
                except:
                    continue
            
            page.wait_for_timeout(8000)
            print("[SCRAPER] Giriş işlemi tamamlandı.")
            return True
        except Exception as e:
            print(f"[SCRAPER] Giriş hatası: {e}")
            return False

    def _fetch_page_html(self, url: str, page_num: int = 1) -> Optional[str]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=self.user_agent)
            
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en']});
            """)
            
            page = context.new_page()
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(8000)
                
                # Giriş ekranındaysak giriş yap
                if page.query_selector("input[type='password']") and page_num == 1 and self.dh_username:
                    print("[SCRAPER] Giriş ekranı tespit edildi, giriş yapılıyor...")
                    if self._login(page):
                        page.goto(url, timeout=60000, wait_until="domcontentloaded")
                        page.wait_for_timeout(8000)
                
                # Mesajların yüklenmesini kesinlikle bekle
                try:
                    page.wait_for_selector("div[data-role='commentContent'], .ipsType_richText", timeout=15000)
                    print("[SCRAPER] Mesaj kutucukları bulundu!")
                except PlaywrightTimeoutError:
                    print("[SCRAPER] Mesaj kutucukları beklenirken zaman aşımı.")
                
                html = page.content()
                return html
                
            except Exception as e:
                print(f"[SCRAPER] Fetch error: {e}")
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

        # En garantili mesaj kutucuğu aramasi
        content_els = soup.find_all("div", attrs={"data-role": "commentContent"})
        if not content_els:
            content_els = soup.find_all("div", class_=re.compile(r"cPost_contentWrap|ipsType_richText", re.I))
        
        if not content_els:
            print(f"Sayfa {page}: post bulunamadi!")
            # Bize ne gördüğünü yazdır
            print("Sayfa Metni (Ilk 1000 karakter):")
            print(soup.get_text(separator=" ", strip=True)[:1000])
            return posts

        print(f"Sayfa {page}: {len(content_els)} adet mesaj bulundu.")

        for el in content_els:
            # Kutucuğun içindeki yazıyı al
            for quote in el.find_all(["blockquote", "div"], class_=re.compile(r"ipsQuote|quote", re.I)):
                quote.decompose()
            content = el.get_text(separator=" ", strip=True)
            content = re.sub(r"\s+", " ", content)
            
            if not content:
                continue

            # Üst kutucuklardan yazar ve id'yi bulmaya çalış
            post_id = ""
            author = ""
            
            parent = el.find_parent("article")
            if not parent:
                parent = el.find_parent(class_=re.compile(r"cPost|ipsComment", re.I))
                
            if parent:
                pid = parent.get("id", "")
                m = re.search(r"\d+", pid)
                if m:
                    post_id = m.group()
                elif parent.get("data-postid"):
                    post_id = parent.get("data-postid")
                    
                author_el = parent.find("a", class_=re.compile(r"ipsType_break|cAuthorPane_author", re.I))
                if author_el:
                    author = author_el.get_text(strip=True)
            
            if not post_id:
                post_id = content[:20]

            posts.append(
                ForumPost(
                    post_id=post_id, author=author, timestamp="", 
                    content=content, url="", page=page,
                )
            )
        return posts

    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        all_posts: List[ForumPost] = []

        html = self._fetch_page_html(self.base_url, page_num=1)
        if not html:
            print("[SCRAPER] Ilk sayfa yuklenemedi!")
            return all_posts

        soup = BeautifulSoup(html, "lxml")
        total_pages = self._get_total_pages(soup)
        pages_to_scan = min(num_pages, total_pages)
        print(f"Toplam {total_pages} sayfa, {pages_to_scan} sayfa taranacak.")

        all_posts.extend(self._parse_posts(html, 1))

        for page in range(2, pages_to_scan + 1):
            time.sleep(self.delay)
            url = self._get_page_url(page)
            print(f"Sayfa {page} yukleniyor: {url}")
            html = self._fetch_page_html(url, page_num=page)
            if html:
                all_posts.extend(self._parse_posts(html, page))

        print(f"Toplam {len(all_posts)} post bulundu.")
        return all_posts
