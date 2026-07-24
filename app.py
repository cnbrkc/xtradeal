import streamlit as st
import pandas as pd
from config import Config
from database import Database
from main import run_scan

# Sayfa ayarları
st.set_page_config(page_title="Araç Teklif Botu", page_icon="🚗", layout="wide")

# Bileşenleri başlat
config = Config()
db = Database(config.DB_PATH)

st.title("🚗 Araç Teklif Botu")
st.markdown("DonanimHaber forumundan sıfır araç tekliflerini tarar, fiyat ve bayi bilgisini çıkarır.")

# İstatistikler
stats = db.get_stats()
col1, col2, col3 = st.columns(3)
col1.metric("Toplam Teklif", stats['total'])
col2.metric("Yüksek Güvenilirlik", stats['high_confidence'])
col3.metric("Telegram'a Gönderilen", stats['sent'])

st.markdown("---")

# Manuel Tarama Butonu
col_btn1, col_btn2 = st.columns([1, 3])
if col_btn1.button("🔍 Şimdi Tara (Manuel)"):
    with st.spinner("Forum taranıyor, bu birkaç saniye sürebilir..."):
        try:
            # Manuel taramada Telegram'a göndermeyelim, sadece veritabanına eklesin
            result = run_scan(config, send_telegram=False)
            st.success(f"Tarama tamamlandı! {result['total_posts']} post bulundu, {result['new_deals']} yeni teklif eklendi.")
        except Exception as e:
            st.error(f"Tarama sırasında bir hata oluştu: {e}")

st.markdown("### 📋 Kayıtlı Teklifler")

# Filtreler
col_f1, col_f2 = st.columns(2)
min_conf = col_f1.slider("Minimum Güven Skoru", 0.0, 1.0, 0.3, 0.1)
brand_filter = col_f2.text_input("Markaya Göre Filtrele (Örn: Volkswagen)")

# Verileri çek
deals = db.get_all_deals(limit=500, min_confidence=min_conf, brand=brand_filter if brand_filter else None)

if deals:
    # DataFrame'e çevirip tablo olarak göster
    df = pd.DataFrame(deals)
    
    # Kolonları düzenle ve sırala
    cols_to_show = ['scanned_at', 'car_brand', 'car_model', 'year', 'price_text', 'dealer', 'author', 'confidence', 'content', 'url']
    df = df[[c for c in cols_to_show if c in df.columns]]
    
    # İsimleri Türkçe yap
    df.columns = ['Tarama Zamanı', 'Marka', 'Model', 'Yıl', 'Fiyat', 'Bayi', 'Paylaşan', 'Güven (%)', 'İçerik', 'Link']
    df['Güven (%)'] = (df['Güven (%)'] * 100).astype(int)
    
    st.dataframe(df, use_container_width=True, height=500, hide_index=True)
else:
    st.info("Henüz teklif bulunamadı. Yukarıdaki 'Şimdi Tara' butonuna basarak bir tarama başlatabilirsiniz.")
