"""
debug_dh.py — DH Forum HTML Yapısı Keşif Scripti
Çalıştır:  python debug_dh.py
"""
from playwright.sync_api import sync_playwright

URL = "https://forum.donanimhaber.com/sifir-arac-ve-arac-fiyati-teklifi-alanlar-2022--132918743"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()
    page.goto(URL, timeout=60000, wait_until="networkidle")
    page.wait_for_timeout(5000)

    # ── HTML'i dosyaya kaydet ──
    html = page.content()
    with open("dh_debug.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML kaydedildi ({len(html)} karakter) → dh_debug.html")

    # ── Olası mesaj container'larını ara ──
    print("\n=== OLASI MESAJ YAPILARI ===")
    selectors = [
        "div[class*='mesaj']",  "div[class*='Mesaj']",
        "div[class*='msg']",    "div[class*='Msg']",
        "div[class*='post']",   "div[class*='Post']",
        "div[class*='comment']", "div[class*='cevap']",
        "div[class*='content']", "div[class*='Content']",
        "div[id*='msg']",       "article",
        "div[class*='klasik']", "div[class*='birMesaj']",
        "div[class*='yanit']",  "div[class*='Yanit']",
    ]
    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count > 0:
                print(f"  ✅ {sel}  →  {count} adet")
                snippet = page.locator(sel).first.inner_html()[:400]
                print(f"     Örnek: {snippet}\n")
        except:
            pass

    # ── Pagination linklerini bul ──
    print("\n=== SAYFA 2 LİNKİ ===")
    links = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .filter(a => {
                const t = a.textContent.trim();
                const h = a.getAttribute('href') || '';
                return t === '2' || t === 'sonraki' || h.endsWith('-2');
            })
            .slice(0, 5)
            .map(a => ({ text: a.textContent.trim(), href: a.getAttribute('href') }));
    }""")
    for lk in links:
        print(f"  '{lk['text']}'  →  {lk['href']}")

    browser.close()
    print("\n🔍 dh_debug.html dosyasını VS Code ile açıp incele!")
