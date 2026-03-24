"""
=============================================================
SCRIPT UNTUK MENDOWNLOAD DATA BERITA HIGH IMPACT DARI WEB
=============================================================
Jalankan script ini untuk mengisi file high_impact_news.csv
dengan data berita dari ForexFactory.

CARA MANUAL (Jika script ini gagal):
1. Buka https://www.forexfactory.com/calendar
2. Klik filter (ikon corong) -> centang hanya "High Impact"
3. Pilih rentang tanggal yang diinginkan
4. Catat tanggal, waktu (UTC), dan judul berita
5. Masukkan ke file high_impact_news.csv dengan format:
   date,time_utc,currency,impact,title
   2026-03-24,13:45,USD,High,Flash Manufacturing PMI
"""

import csv
import os
import requests
from datetime import datetime

FILE_OUTPUT = os.path.join(os.path.dirname(__file__), "high_impact_news.csv")

def download_dari_api():
    """Mencoba download dari API ForexFactory (faireconomy.media)"""
    urls = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    ]
    
    semua_berita = []
    
    for url in urls:
        try:
            print(f"Mengambil data dari {url}...")
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.text.startswith('['):
                data = r.json()
                for event in data:
                    if event.get('country') == 'USD' and event.get('impact') == 'High':
                        waktu_str = event.get('date', '')
                        title = event.get('title', '')
                        if waktu_str:
                            try:
                                dt = datetime.fromisoformat(waktu_str.replace('Z', '+00:00'))
                                semua_berita.append({
                                    'date': dt.strftime('%Y-%m-%d'),
                                    'time_utc': dt.strftime('%H:%M'),
                                    'currency': 'USD',
                                    'impact': 'High',
                                    'title': title
                                })
                            except (ValueError, TypeError):
                                continue
                print(f"  Berhasil: {len(data)} event ditemukan")
            else:
                print(f"  Gagal: Status {r.status_code}")
        except Exception as e:
            print(f"  Error: {e}")
    
    return semua_berita

def simpan_ke_csv(berita_list):
    """Simpan data berita ke CSV. Append jika sudah ada data sebelumnya."""
    # Baca data existing
    existing = set()
    if os.path.exists(FILE_OUTPUT):
        with open(FILE_OUTPUT, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = f"{row.get('date','')}_{row.get('time_utc','')}_{row.get('title','')}"
                existing.add(key)
    
    # Filter berita baru
    berita_baru = []
    for b in berita_list:
        key = f"{b['date']}_{b['time_utc']}_{b['title']}"
        if key not in existing:
            berita_baru.append(b)
    
    if not berita_baru:
        print("\nTidak ada berita baru untuk ditambahkan.")
        return
    
    # Tulis semua data
    mode = 'a' if os.path.exists(FILE_OUTPUT) and os.path.getsize(FILE_OUTPUT) > 0 else 'w'
    with open(FILE_OUTPUT, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'time_utc', 'currency', 'impact', 'title'])
        if mode == 'w':
            writer.writeheader()
        writer.writerows(berita_baru)
    
    print(f"\n✅ {len(berita_baru)} berita baru ditambahkan ke {FILE_OUTPUT}")

if __name__ == "__main__":
    print("=" * 50)
    print("📰 DOWNLOAD DATA BERITA HIGH IMPACT USD")
    print("=" * 50)
    
    berita = download_dari_api()
    
    if berita:
        print(f"\nDitemukan {len(berita)} berita High Impact USD:")
        for b in berita:
            print(f"  {b['date']} {b['time_utc']} - {b['title']}")
        simpan_ke_csv(berita)
    else:
        print("\n⚠️ Tidak bisa mengambil data dari API.")
        print("Silakan isi file CSV secara manual.")
        print(f"File: {FILE_OUTPUT}")
        print("\nFormat CSV:")
        print("date,time_utc,currency,impact,title")
        print("2026-03-24,13:45,USD,High,Flash Manufacturing PMI")
    
    print(f"\n📄 File CSV: {FILE_OUTPUT}")
    if os.path.exists(FILE_OUTPUT):
        with open(FILE_OUTPUT, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"Isi saat ini:\n{content}")
