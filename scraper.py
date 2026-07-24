"""
DonanimHaber forum scraper.
Cloudscraper ile güvenlik duvarı (Cloudflare) aşımı yapar.
"""
import re
import time
import cloudscraper
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin


@dataclass
class ForumPost:
    post_id: str
    author: str
    timestamp: str
    content: str
    url: str
    page: int
    raw_html: str = ""


class DonanimHaberScraper:
    def __init__(self, base_url: str, user_agent: str, delay: float = 2.0):
        self.base_url = base_url
        # requests.Session yerine cloudscraper kullanıyoruz
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://www.google.com/",
            }
        )
        self.delay = delay

    # ------------------------------------------------------------------ #
    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            resp = self.session.get(url, timeout=45, allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            print(f"[SCRAPER] Fetch error {url}: {e}")
            return None

    def _get_page_url(self, page: int) -> str:
        if page <= 1:
            return self.base_url
        sep = "&" if "?" in self.base_url else "?"
        return f"{self.base_url}{sep}page={page}"

    # ------------------------------------------------------------------ #
    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Pagination'dan toplam sayfa sayısını bul."""
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

        text = soup.get_text()
        m = re.search(r"(\d+)\s* /\s* \d+\s*sayfa", text, re.I)
        if m:
            return int(m.group(1))
        return 1

    # ------------------------------------------------------------------ #
    def _parse_posts(self, html: str, page: int) -> List[ForumPost]:
        soup = BeautifulSoup(html, "lxml")
        posts: List[ForumPost] = []

        # --- IPS Community article yapısı ---
        articles = soup.find_all("article", id=re.compile(r"elComment_\d+"))

        if not articles:
            articles = soup.find_all(attrs={"data-postid": True})

        if not articles:
            articles = soup.find_all("div", class_=re.compile(r"cPost|ipsComment"))

        if not articles:
            print(f"[SCRAPER] Sayfa {page}: post bulunamadı! HTML yapısı değişmiş olabilir.")
            # Sadece ilk 500 karakteri basacak, güvenlik duvarı yüzünden mi boş diye anlamak için
            print(f"[SCRAPER] Gelen HTML özeti: {soup.get_text()[:500]}")
            return posts

        for article in articles:
            # --- post_id ---
            post_id = ""
            pid = article.get("id", "")
            m = re.search(r"\d+", pid)
            if m:
                post_id = m.group()
            elif article.get("data-postid"):
                post_id = article.get("data-postid")
            if not post_id:
                continue

            # --- author ---
            author = ""
            author_el = article.find("a", class_=re.compile(r"ipsType_break|author|username", re.I))
            if not author_el:
                aside = article.find("aside")
                if aside:
                    author_el = aside.find("a", href=True)
            if author_el:
                author = author_el.get_text(strip=True)

            # --- timestamp ---
            timestamp = ""
            time_el = article.find("time")
            if time_el:
                timestamp = time_el.get("datetime", "") or time_el.get("title", "") or time_el.get_text(strip=True)
            if not timestamp:
                ts_el = article.find(attrs={"data-timestamp": True})
                if ts_el:
                    timestamp = ts_el.get("data-timestamp", "")

            # --- content ---
            content = ""
            content_el = article.find(
                "div",
                class_=re.compile(r"cPost_contentWrap|ipsType_normal|post_content|ipsComment_content", re.I),
            )
            if not content_el:
                content_el = article.find("div", class_=re.compile(r"post_message|messageContent", re.I))
            if content_el:
                # Alıntıları temizle
                for quote in content_el.find_all(["blockquote", "div"], class_=re.compile(r"ipsQuote|quote", re.I)):
                    quote.decompose()
                # Edit notlarını temizle
                for edit in content_el.find_all(attrs={"class": re.compile(r"ipsEdit|edit", re.I)}):
                    edit.decompose()
                content = content_el.get_text(separator=" ", strip=True)
                content = re.sub(r"\s+", " ", content)

            # --- post URL (permalink) ---
            post_url = ""
            share_el = article.find("a", class_=re.compile(r"ipsType_blendLinks|share|permalink", re.I))
            if share_el:
                post_url = share_el.get("href", "")
            if not post_url:
                link_el = article.find(attrs={"data-link": True})
                if link_el:
                    post_url = link_el.get("data-link", "")
            if post_url and not post_url.startswith("http"):
                post_url = urljoin(self.base_url, post_url)

            posts.append(
                ForumPost(
                    post_id=post_id,
                    author=author,
                    timestamp=timestamp,
                    content=content,
                    url=post_url,
                    page=page,
                )
            )

        return posts

    # ------------------------------------------------------------------ #
    def scrape(self, num_pages: int = 5) -> List[ForumPost]:
        all_posts: List[ForumPost] = []

        # İlk sayfa
        html = self._fetch_page(self.base_url)
        if not html:
            print("[SCRAPER] İlk sayfa yüklenemedi! Güvenlik duvarı engellemiş olabilir.")
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
            html = self._fetch_page(url)
            if html:
                all_posts.extend(self._parse_posts(html, page))
            else:
                print(f"[SCRAPER] Sayfa {page} yüklenemedi, atlanıyor.")

        print(f"[SCRAPER] Toplam {len(all_posts)} post bulundu.")
        return all_posts
