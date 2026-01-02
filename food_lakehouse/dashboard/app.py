import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime

st.set_page_config(page_title="Sanrio Rec", layout="wide", page_icon="🍱")
engine = create_engine(os.getenv("DATABASE_URL"))

st.markdown("""
<style>
[data-testid="stMetricValue"] {
    font-size: 20px !important;
    white-space: break-spaces !important;
    word-wrap: break-word !important;
    line-height: 1.2 !important;
}
</style>
""", unsafe_allow_html=True)

def get_schedule_from_csv():
    file_path = '/app/data_source/jadwal_kuliah.csv'
    try:
        df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig')
        
        if df.shape[1] == 1:
            df = pd.read_csv(file_path, sep=',', encoding='utf-8-sig')

        df.columns = df.columns.str.strip().str.lower()
        
        rename_map = {}
        for col in df.columns:
            if 'hari' in col or 'day' in col:
                rename_map[col] = 'Hari'
            elif 'selesai' in col or 'end' in col:
                rename_map[col] = 'Jam_Selesai'
            elif 'mulai' in col or 'start' in col:
                rename_map[col] = 'Jam_Mulai'
            elif 'kuliah' in col or 'mata' in col or 'subject' in col:
                rename_map[col] = 'Mata_Kuliah'
        
        df.rename(columns=rename_map, inplace=True)
        
        if 'Hari' in df.columns:
            df['Hari'] = df['Hari'].astype(str).str.strip().str.capitalize()
            
        return df
    except Exception as e:
        print(f"Error Baca CSV: {e}")
        return pd.DataFrame()

def get_today_indo():
    days_map = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    today_sys = datetime.now().strftime('%A')
    return days_map.get(today_sys, 'Minggu')

st.sidebar.header("⚙️ User Control Panel")
try:
    with engine.connect() as conn:
        config = pd.read_sql("SELECT * FROM user_configs ORDER BY updated_at DESC LIMIT 1", conn).iloc[0]

    with st.sidebar.form("input_form"):
        loc = st.text_input("Lokasi Kamu", value=config['target_location'])
        budget = st.number_input("Budget Saat Ini", value=int(config['budget_amount']))
        submit = st.form_submit_button("Dapatkan Rekomendasi!")

        if submit:
            with engine.connect() as conn:
                query = text("UPDATE user_configs SET target_location=:l, budget_amount=:b, updated_at=NOW()")
                conn.execute(query, {'l': loc, 'b': budget})
                conn.commit()
            st.sidebar.success("✅ Silakan Refresh Dashboard Kamu!")
except:
    st.sidebar.warning("Menunggu Database Ready...")

st.title("🍱 Smart Food Recommendation System")
st.markdown("### Integrasi Data Lakehouse (SQL + CSV + API + Web Scraping)")

if st.button("🔄 Refresh Dashboard"):
    st.rerun()

try:
    df_gold = pd.read_sql("SELECT * FROM gold_recommendations ORDER BY generated_at DESC LIMIT 1", engine)
    
    df_csv = get_schedule_from_csv()
    hari_ini = get_today_indo()
    
    if not df_csv.empty and 'Hari' in df_csv.columns:
        jadwal_today = df_csv[df_csv['Hari'] == hari_ini]
        jumlah_kelas = len(jadwal_today)
        if not jadwal_today.empty:
            jam_pulang = jadwal_today['Jam_Selesai'].max()
            info_kuliah = f"{jumlah_kelas} Matkul (Sampai {jam_pulang})"
        else:
            info_kuliah = "Libur / Tidak Ada Kelas"
    else:
        info_kuliah = "Gagal Baca CSV (Cek Format)"

    col1, col2, col3, col4 = st.columns(4)

    if not df_gold.empty:
        data = df_gold.iloc[0]
        icon_cuaca = "🌧️" if data['weather_condition'] in ['Rain', 'Thunderstorm'] else "☀️"
        
        col1.metric("1. Cuaca", f"{icon_cuaca} {data['weather_condition']}")
        
        col2.metric("2. Jadwal", info_kuliah, delta=f"Hari: {hari_ini}")
        
        promo_text = data.get('promo_info', 'Data Lama/Kosong')
        col3.metric("3. Promo", promo_text)
        
        col4.metric("4. Rekomendasi", data['recommendation'])
        
        st.info(f"**💡 Alasan Sistem:** {data['logic_explanation']}")
    else:
        st.warning("⚠️ Data ETL belum masuk.")

    st.divider()
    
    tab1, tab2 = st.tabs(["📅 Tabel Jadwal Kuliah", "📜 Riwayat Rekomendasi"])

    with tab1:
        st.write(f"Data mentah dari `jadwal_kuliah.csv`. Filter hari ini (**{hari_ini}**):")
        if df_csv.empty:
            st.error("❌ File CSV kosong atau tidak ditemukan. Cek folder `data_source`.")
        elif 'Hari' not in df_csv.columns:
            st.error(f"❌ Kolom 'Hari' tidak ditemukan. Kolom yang terbaca: {df_csv.columns.tolist()}")
            st.dataframe(df_csv) 
        else:
            def highlight_today(s):
                return ['background-color: #d1f5d3' if s['Hari'] == hari_ini else '' for _ in s]
            
            st.dataframe(df_csv.style.apply(highlight_today, axis=1), use_container_width=True)

    with tab2:
        df_history = pd.read_sql("""
            SELECT generated_at as "Waktu", 
                   weather_condition as "Cuaca", 
                   current_budget_status as "Info Budget",
                   promo_info as "Info Promo",
                   recommendation as "Keputusan", 
                   logic_explanation as "Alasan"
            FROM gold_recommendations ORDER BY generated_at DESC LIMIT 10
        """, engine)
        st.dataframe(df_history, use_container_width=True)

except Exception as e:
    st.error(f"Terjadi Kesalahan Sistem: {e}")