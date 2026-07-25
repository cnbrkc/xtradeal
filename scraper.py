"""
DonanimHaber forum scraper (Playwright ile).
Güvenlik duvarını aşar, üye girişi yapar ve mesajları okur.
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
            print("[SCRAPER] DH kullanıcı adı/şifre yok, giriş yapılamadı!")
            return False
            
        print("[SCRAPER] Forum'a giriş yapılıyor...")
        try:
            page.goto("https://forum.donanimhaber.com/login/", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            print("[SCRAPER] Giriş kutucukları aranıyor...")
            page.wait_for_selector("input[type='password']", timeout=15000)
            
            page.locator("input[type='password']").first.fill(self.dh_password)
            
            username_selectors = ["input[name='auth']", "input[name='username']", "input[type='email']", "input[type='text']"]
            for sel in username_selectors:
                try:
                    if page.locator(sel).first.is_visible():
                        page.locator(sel).first.fill(self.dh_username)
                        print("Kullanıcı adı yazıldı.")
                        break
                except:
                    continue
            
            print("[SCRAPER] Giriş yap butonuna tıklanıyor...")
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
                
                # Sayfada mesaj kutucukları var mı kontrol et
                has_posts = page.query_selector("article, .ipsComment, .cPost")
                
                if not has_posts and page_num == 1 and self.dh_username and self.dh_password:
                    print("[SCRAPER] Mesaj bulunamadı, üye girişi yapılıyor...")
                    logged_in = self._login(page)
                    if logged_in:
                        print("[SCRAPER] Giriş yapıldı, konuya tekrar dönülüyor...")
                        page.goto(url, timeout=60000, wait_until="domcontentloaded")
                        page.wait_for_timeout(8000)
                
                # Sayfanın tamamen yüklenmesi için ekstra bekle
                page.wait_for_timeout(2000)
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

        # DH'nin yeni yapısına göre çok geniş arama
        articles = soup.find_all("article")
        if not articles:
            articles = soup.find_all("div", class_=re.compile(r"ipsComment|cPost", re.I))
        if not articles:
            articles = soup.find_all("div", attrs={"data-postid": True})
        if not articles:
            articles = soup.find_all("div", attrs={"data-commentid": True})

        if not articles:
            print(f"Sayfa {page}: post bulunamadı!")
            return posts

        for article in articles:
            post_id = ""
            pid = article.get("id", "")
            m = re.search(r"\d+", pid)
            if m:
                post_id = m.group()
            elif article.get("data-postid"):
                post_id = article.get("data-postid")
            elif article.get("data-commentid"):
                post_id = article.get("data-commentid")
            
            # İçerik olup olmadığını kontrol et (Menü vs. ise atla)
            content_el = article.find("div", attrs={"data-role": "commentContent"})
            if not content_el:
                content_el = article.find("div", class_=re.compile(r"cPost_contentWrap|ipsType_richText", re.I))
            if not content_el:
                content_el = article.find("div", class_=re.compile(r"post_message|messageContent", re.I))
            
            if not content_el:
                continue

            # Yazar bulma
            author = ""
            author_el = article.find("a", class_=re.compile(r"ipsType_break|cAuthorPane_author", re.I))
            if not author_el:
                author_el = article.find("span", class_=re.compile(r"author", re.I))
            if author_el:
                author = author_el.get_text(strip=True)

            # Zaman bulma
            timestamp = ""
            time_el = article.find("time")
            if time_el:
                timestamp = time_el.get("datetime", "") or time_el.get_text(strip=True)

            # İçeriği temizleme
            for quote in content_el.find_all(["blockquote", "div"], class_=re.compile(r"ipsQuote|quote", re.I)):
                quote.decompose()
            for edit in content_el.find_all(attrs={"class": re.compile(r"ipsEdit|edit", re.I)}):
                edit.decompose()
            content = content_el.get_text(separator=" ", strip=True)
            content = re.sub(r"\s+", " ", content)

            if not content:
                continue

            # URL bulma
            post_url = ""
            share_el = article.find("a", class_=re.compile(r"ipsType_blendLinks|share|permalink", re.I))
            if not share_el:
                share_el = article.find("a", attrs={"data-role": "shareComment"})
            if share_el:
                post_url = share_el.get("href", "")
            if post_url and not post_url.startswith("http"):
                post_url = urljoin(self.base_url, post_url)

            if not post_id:
                post_id = content[:20] # Yedek ID

            posts.append(
                ForumPost(
                    post_id=post_id, author=author, timestamp=timestamp,
                    content=content, url=post_url, page=page,
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
