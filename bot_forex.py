import MetaTrader5 as mt5
import pandas as pd
import time
import csv
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ==========================================
# 1. KONFIGURASI UTAMA LIVE TRADING
# ==========================================
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M5
LOT = 0.01                      # <--- Ubah manual jika saldo sudah naik
SL_PIPS = 50
RR_RATIO = 3
MAGIC_NUMBER = 999111
DEVIATION = 20
MAKSIMAL_POSISI = 1

# --- SETTING BREAKOUT KOTAK ---
PERIODE_KOTAK = 4               # Konsolidasi 4 candle (20 Menit)
MAKS_LEBAR_KOTAK_PIPS = 50      # Lebar kotak maksimal 50 Pips ($5.0)

# --- SETTING BREAKEVEN (BE) ---
GUNAKAN_BE = True               
TARGET_BE_PIPS = 30             # Geser SL ke Entry jika profit 30 Pips

# --- SETTING BERITA ---
JEDA_BERITA_MENIT = 60          
FILE_BERITA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_high_impact_news.csv")

_cache_berita = {'data': [], 'terakhir_update': None}

# ==========================================
# 2. FUNGSI BERITA OTOMATIS & FILTER
# ==========================================
def update_berita_otomatis():
    """Download jadwal berita High Impact USD minggu ini dari Forex Factory."""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    print("🌐 Mengunduh jadwal berita terbaru dari Forex Factory...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        root = ET.fromstring(response.read())
        
        berita_baru = []
        for event in root.findall('event'):
            currency = event.find('country').text
            impact = event.find('impact').text
            if currency == 'USD' and impact == 'High':
                tgl_str, waktu_str, judul = event.find('date').text, event.find('time').text, event.find('title').text
                try:
                    tgl_format = datetime.strptime(tgl_str, "%m-%d-%Y").strftime("%Y-%m-%d")
                    waktu_format = datetime.strptime(waktu_str, "%I:%M%p").strftime("%H:%M")
                    berita_baru.append({'date': tgl_format, 'time_utc': waktu_format, 'currency': currency, 'impact': 'High', 'title': judul})
                except ValueError: continue
                
        with open(FILE_BERITA, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'time_utc', 'currency', 'impact', 'title'])
            writer.writeheader()
            writer.writerows(berita_baru)
        print(f"✅ Auto-Update Berita Sukses! ({len(berita_baru)} Berita High Impact USD tersimpan)")
    except Exception as e:
        print(f"⚠️ Gagal update berita otomatis: {e}. Menggunakan CSV lama.")

def muat_berita_dari_csv():
    global _cache_berita
    sekarang = datetime.now(timezone.utc)
    if _cache_berita['terakhir_update'] and (sekarang - _cache_berita['terakhir_update']).total_seconds() < 600:
        return _cache_berita['data']
    
    jadwal = []
    if os.path.exists(FILE_BERITA):
        with open(FILE_BERITA, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('currency', '') == 'USD' and row.get('impact', '') == 'High':
                    try:
                        waktu_event = datetime.strptime(f"{row['date']} {row['time_utc']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                        jadwal.append({'waktu': waktu_event, 'judul': row.get('title', 'Unknown')})
                    except: continue
    
    _cache_berita['data'] = jadwal
    _cache_berita['terakhir_update'] = sekarang
    return jadwal

def ada_berita_high_impact():
    jadwal = muat_berita_dari_csv()
    sekarang = datetime.now(timezone.utc)
    for berita in jadwal:
        selisih = abs((sekarang - berita['waktu']).total_seconds())
        if selisih <= JEDA_BERITA_MENIT * 60:
            print(f"📰 AWAS! Berita: \"{berita['judul']}\" dalam {int(selisih / 60)} menit.")
            return True
    return False

# ==========================================
# 3. FUNGSI TRADING MT5 (BREAKOUT & BE)
# ==========================================
def inisialisasi_mt5():
    if not mt5.initialize() or not mt5.symbol_select(SYMBOL, True):
        print("Gagal terhubung ke MT5 atau memuat simbol.")
        return False
    print(f"🚀 Bot Live Breakout Aktif! Simbol: {SYMBOL} | Lot: {LOT}")
    return True

def hitung_posisi_terbuka():
    posisi = mt5.positions_get(symbol=SYMBOL)
    return len([p for p in posisi if p.magic == MAGIC_NUMBER]) if posisi else 0

def dapatkan_nilai_1_pip():
    symbol_info = mt5.symbol_info(SYMBOL)
    return 0.1 if "XAU" in SYMBOL else (10 if symbol_info.digits in [3, 5] else 1) * symbol_info.point

def urus_breakeven():
    """Mengecek posisi terbuka dan menggeser SL ke Entry jika target BE tercapai."""
    if not GUNAKAN_BE: return
    posisi = mt5.positions_get(symbol=SYMBOL)
    if not posisi: return

    jarak_be_harga = TARGET_BE_PIPS * dapatkan_nilai_1_pip()

    for p in posisi:
        if p.magic != MAGIC_NUMBER: continue

        # Jika posisi BUY
        if p.type == mt5.ORDER_TYPE_BUY:
            if mt5.symbol_info_tick(SYMBOL).bid >= (p.price_open + jarak_be_harga):
                if p.sl < p.price_open: # Jika SL masih di bawah harga Entry
                    request = {"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": SYMBOL, "sl": p.price_open, "tp": p.tp}
                    if mt5.order_send(request).retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"🛡️ BREAKEVEN AKTIF! Posisi BUY ({p.ticket}) SL diamankan ke Entry: {p.price_open}")

        # Jika posisi SELL
        elif p.type == mt5.ORDER_TYPE_SELL:
            if mt5.symbol_info_tick(SYMBOL).ask <= (p.price_open - jarak_be_harga):
                if p.sl > p.price_open or p.sl == 0.0: # Jika SL masih di atas harga Entry
                    request = {"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": SYMBOL, "sl": p.price_open, "tp": p.tp}
                    if mt5.order_send(request).retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"🛡️ BREAKEVEN AKTIF! Posisi SELL ({p.ticket}) SL diamankan ke Entry: {p.price_open}")

def analisa_sinyal():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 250)
    df = pd.DataFrame(rates)
    if len(df) < 201: return "TUNGGU"
    
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['Box_High'] = df['high'].shift(1).rolling(window=PERIODE_KOTAK).max()
    df['Box_Low'] = df['low'].shift(1).rolling(window=PERIODE_KOTAK).min()
    
    c_valid = df.iloc[-2]
    
    syarat_lebar_kotak_harga = MAKS_LEBAR_KOTAK_PIPS * dapatkan_nilai_1_pip()
    lebar_kotak_aktual = c_valid['Box_High'] - c_valid['Box_Low']
    kotak_valid = lebar_kotak_aktual <= syarat_lebar_kotak_harga
    
    breakout_buy = c_valid['close'] > c_valid['Box_High']
    breakout_sell = c_valid['close'] < c_valid['Box_Low']
    
    if (c_valid['close'] > c_valid['EMA_200']) and kotak_valid and breakout_buy:
        return "BUY"
    elif (c_valid['close'] < c_valid['EMA_200']) and kotak_valid and breakout_sell:
        return "SELL"
        
    return "TUNGGU"

def eksekusi_order(sinyal):
    nilai_1_pip = dapatkan_nilai_1_pip()
    jarak_sl_harga = SL_PIPS * nilai_1_pip
    jarak_tp_harga = (SL_PIPS * RR_RATIO) * nilai_1_pip
    
    tick = mt5.symbol_info_tick(SYMBOL)
    
    if sinyal == "BUY":
        harga_open, sl, tp = tick.ask, tick.ask - jarak_sl_harga, tick.ask + jarak_tp_harga
        tipe_order = mt5.ORDER_TYPE_BUY
    elif sinyal == "SELL":
        harga_open, sl, tp = tick.bid, tick.bid + jarak_sl_harga, tick.bid - jarak_tp_harga
        tipe_order = mt5.ORDER_TYPE_SELL
        
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": float(LOT),
        "type": tipe_order,
        "price": harga_open,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": DEVIATION,
        "magic": MAGIC_NUMBER,
        "comment": "Bot Breakout + BE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    hasil = mt5.order_send(request)
    if hasil.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Order Gagal! Error code: {hasil.retcode}")
    else:
        print(f"✅ Order {sinyal} Berhasil! Harga: {harga_open}, SL: {sl:.2f}, TP: {tp:.2f}")

# ==========================================
# 4. JANTUNG BOT (MAIN LOOP)
# ==========================================
if __name__ == "__main__":
    update_berita_otomatis() # Download berita terbaru saat bot pertama kali dinyalakan
    
    if inisialisasi_mt5():
        print("Bot mulai memantau pasar. Tekan Ctrl+C untuk berhenti.")
        try:
            while True:
                # 1. Cek dan amankan posisi dengan Breakeven SETIAP DETIK
                urus_breakeven()
                
                # 2. Cek apakah boleh buka posisi baru
                jumlah_posisi_sekarang = hitung_posisi_terbuka()
                if jumlah_posisi_sekarang >= MAKSIMAL_POSISI:
                    time.sleep(5) # Istirahat sebentar jika garasi penuh
                    continue 
                
                # 3. Cek Satpam Berita
                if ada_berita_high_impact():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Zona Merah News! Bot tiarap ±{JEDA_BERITA_MENIT} menit.")
                    time.sleep(60) 
                    continue
                    
                # 4. Cari Sinyal Breakout
                sinyal_sekarang = analisa_sinyal()
                
                # 5. Eksekusi
                if sinyal_sekarang in ["BUY", "SELL"]:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 Sinyal {sinyal_sekarang} Valid! Menerobos Kotak Konsolidasi!")
                    eksekusi_order(sinyal_sekarang)
                    print("Bot jeda 15 menit agar tidak spam posisi ganda...")
                    time.sleep(900) 
                
                time.sleep(1) # Cek pergerakan harga setiap 1 detik
                
        except KeyboardInterrupt:
            print("\nBot dihentikan oleh pengguna.")
        finally:
            mt5.shutdown()