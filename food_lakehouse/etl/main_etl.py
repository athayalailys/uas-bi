import os
import time
import json
import uuid
import pandas as pd
from sqlalchemy import create_engine
from minio import Minio
from datetime import datetime
import io
import requests
from bs4 import BeautifulSoup
import pytz # Library untuk Timezone Indonesia


def get_wita_now():
    utc_now = datetime.now(pytz.utc)
    wita_now = utc_now.astimezone(pytz.timezone('Asia/Makassar'))
    return wita_now.replace(tzinfo=None)

print("Menunggu service lain siap (10 detik)...")
time.sleep(10)

db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False
)
BUCKET_BRONZE = "bronze-weather-raw"
if not minio_client.bucket_exists(BUCKET_BRONZE):
    minio_client.make_bucket(BUCKET_BRONZE)


def get_user_config():
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM user_configs ORDER BY updated_at DESC LIMIT 1", conn).iloc[0]

def get_schedule_today():
    try:
        file_path = '/app/data_source/jadwal_kuliah.csv'
        df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig')
        if df.shape[1] == 1: 
            df = pd.read_csv(file_path, sep=',', encoding='utf-8-sig')
        
        df.columns = df.columns.str.strip().str.lower()
        rename_map = {}
        for col in df.columns:
            if 'hari' in col: rename_map[col] = 'Hari'
            elif 'selesai' in col: rename_map[col] = 'Jam_Selesai'
            elif 'kuliah' in col: rename_map[col] = 'Mata_Kuliah'
        df.rename(columns=rename_map, inplace=True)
        
        if 'Hari' in df.columns: 
            df['Hari'] = df['Hari'].astype(str).str.strip().str.capitalize()

        wita_now = get_wita_now()
        days_map = {
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu', 
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        }
        today_sys = wita_now.strftime('%A')
        hari_indo = days_map.get(today_sys, 'Minggu')
        
        jadwal = df[df['Hari'] == hari_indo]
        if not jadwal.empty:
            list_matkul = ", ".join(jadwal['Mata_Kuliah'].tolist())
            jam_terakhir = jadwal['Jam_Selesai'].max()
            jumlah_kelas = len(jadwal)
            return list_matkul, jam_terakhir, jumlah_kelas
        
        return "Libur / Tidak Ada Kelas", "00:00", 0
    except Exception as e:
        print(f"Error Reading CSV: {e}")
        return "Error CSV", "00:00", 0

def get_weather_api(city):
    api_key = os.getenv("OPENWEATHER_KEY")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {"main": data['weather'][0]['main'], "temp": data['main']['temp']}
    except:
        pass
    import random
    return {"main": random.choice(['Rain', 'Clear', 'Clouds']), "temp": 29.5}

def scrape_promos():
    try:
        with open('/app/data_source/promo_gojek.html', 'r') as f:
            soup = BeautifulSoup(f, 'lxml')
        promos = []
        for card in soup.find_all('div', class_='card-promo'):
            title = card.find('h3', class_='title').text
            disc = card.find('span', class_='discount-value').text
            promos.append(f"{title} ({disc})")
        return promos if promos else ["Tidak ada promo"]
    except Exception as e:
        print(f"⚠️ Warning Log: Gagal scraping promo karena {e}")
        return ["Promo Tidak Tersedia"]

def run_pipeline():
    waktu_sekarang = get_wita_now()
    print(f"\n--- 🚀 START PIPELINE: {waktu_sekarang} (WITA) ---")
    
    config = get_user_config()
    budget = float(config['budget_amount'])
    
    matkul, jam_pulang, jml_kelas = get_schedule_today()
    
    weather = get_weather_api(config['target_location'])
    
    promos = scrape_promos()
    promo_top = promos[0]
    
    raw_data = {
        "timestamp": str(waktu_sekarang),
        "sql_budget": budget,
        "csv_schedule": {"matkul": matkul, "jam_pulang": jam_pulang},
        "api_weather": weather,
        "web_promo": promos
    }
    json_bytes = json.dumps(raw_data).encode('utf-8')
    filename = f"log_{int(time.time())}.json"
    
    minio_client.put_object(
        BUCKET_BRONZE, filename, io.BytesIO(json_bytes), len(json_bytes), content_type="application/json"
    )

    silver_data = {
        'log_id': str(uuid.uuid4()),
        'timestamp': waktu_sekarang,
        'city': config['target_location'],
        'condition': weather['main'],
        'temp': weather['temp']
    }
    pd.DataFrame([silver_data]).to_sql('silver_weather', engine, if_exists='append', index=False)

    
    is_hujan = weather['main'] in ['Rain', 'Thunderstorm', 'Drizzle']
    try:
        jam_pulang_int = int(str(jam_pulang).split(':')[0])
    except:
        jam_pulang_int = 0
    is_sibuk = (jml_kelas > 1) or (jam_pulang_int >= 15)
    
    has_promo = "50%" in promo_top

    rekomendasi = ""
    alasan = ""
        
    if budget < 20000:
        rekomendasi = "Masak Nasi Goreng / Telur"
        alasan = f"⚠️ ALERT BUDGET: Sisa uangmu cuma Rp {budget:,.0f}. Jangan jajan dulu!"
        
    elif budget < 50000:
        if is_sibuk:
            rekomendasi = "Bungkus di Warung Murah"
            alasan = f"Budget mepet (Rp {budget:,.0f}) & sibuk kuliah. Cari warung murah meriah."
        else:
            rekomendasi = "Masak Sendiri"
            alasan = f"Budget tinggal Rp {budget:,.0f}, tapi jadwal santai. Masak sendiri jauh lebih hemat."
            
    else:
        if is_hujan:
            if has_promo:
                rekomendasi = f"Delivery Pakai Promo ({promo_top})"
                alasan = "Uang aman, Hujan deras, plus ada Promo Gede. Waktunya manjakan diri!"
            else:
                rekomendasi = "Delivery Makanan Berkuah"
                alasan = "Budget aman. Hujan bikin malas keluar, pesan antar saja biar nyaman."
        
        elif is_sibuk:
            rekomendasi = "Makan di Resto Dekat Kampus"
            alasan = "Jadwal padat hari ini. Gunakan budget untuk beli makanan jadi biar hemat waktu."
            
        else:
            rekomendasi = "Nongkrong Gas!"
            alasan = f"Status Keuangan Sehat (Rp {budget:,.0f}). Jadwal santai & cuaca cerah. Self-reward!"

    gold_data = {
        'generated_at': waktu_sekarang,
        'weather_condition': weather['main'],
        'current_budget_status': f"Sisa: Rp {budget:,.0f}",
        'promo_info': promo_top,
        'recommendation': rekomendasi,
        'logic_explanation': alasan
    }
    pd.DataFrame([gold_data]).to_sql('gold_recommendations', engine, if_exists='append', index=False)
    
    print(f"✅ KEPUTUSAN: {rekomendasi} | Promo: {promo_top}")

if __name__ == "__main__":
    while True:
        try:
            run_pipeline()
        except Exception as e:
            print(f"Error Pipeline: {e}")
        
        time.sleep(5)