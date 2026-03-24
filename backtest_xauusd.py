import MetaTrader5 as mt5
import pandas as pd
import csv
import os
from datetime import datetime, timezone

# ==========================================
# 1. KONFIGURASI BACKTEST (BREAKOUT + BE)
# ==========================================
SYMBOL = "XAUUSDm"             
TIMEFRAME = mt5.TIMEFRAME_M5     
JUMLAH_CANDLE = 6000        # 3 Bulan ke belakang
SL_PIPS = 50
RR_RATIO = 3                  # TP otomatis 60 Pips
MAKSIMAL_POSISI = 1

# --- SETTING BREAKOUT ---
PERIODE_KOTAK = 4             # Konsolidasi selama 4 candle (20 Menit)
MAKS_LEBAR_KOTAK_PIPS = 50    # Lebar kotak maksimal 50 Pips ($5.0)

# --- SETTING BREAKEVEN (BARU) ---
GUNAKAN_BE = True             # Aktifkan fitur Breakeven
TARGET_BE_PIPS = 30           # Pindahkan SL ke Entry jika harga sudah profit 30 Pips

# --- SETTING BERITA ---
JEDA_BERITA_MENIT = 60          
FILE_BERITA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "high_impact_news.csv")

# ==========================================
# 2. FUNGSI FILTER BERITA
# ==========================================
def muat_berita_high_impact(waktu_mulai, waktu_akhir):
    jadwal = []
    if not os.path.exists(FILE_BERITA): return jadwal
    try:
        with open(FILE_BERITA, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('currency', '') == 'USD' and row.get('impact', '') == 'High':
                    tgl, jam = row.get('date', ''), row.get('time_utc', '')
                    if tgl and jam:
                        try:
                            waktu_event = datetime.strptime(f"{tgl} {jam}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                            if waktu_mulai <= waktu_event <= waktu_akhir: jadwal.append(waktu_event)
                        except: continue
    except: pass
    return jadwal

def cek_zona_berita(waktu_candle, jadwal_berita, jeda_menit=60):
    for waktu_berita in jadwal_berita:
        if abs((waktu_candle - waktu_berita).total_seconds()) <= jeda_menit * 60: return True
    return False

# ==========================================
# 3. MESIN BACKTEST (DENGAN BE)
# ==========================================
def mulai_backtest():
    if not mt5.initialize():
        print("Gagal terhubung ke MT5!")
        return
        
    print(f"Mengunduh {JUMLAH_CANDLE} data historis {SYMBOL}...")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, JUMLAH_CANDLE)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print("Menganalisa Zona Konsolidasi & Sinyal...")
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['Box_High'] = df['high'].shift(1).rolling(window=PERIODE_KOTAK).max()
    df['Box_Low'] = df['low'].shift(1).rolling(window=PERIODE_KOTAK).min()
    
    nilai_1_pip = 0.1 if "XAU" in SYMBOL else (10 if mt5.symbol_info(SYMBOL).digits in [3, 5] else 1) * mt5.symbol_info(SYMBOL).point
        
    jarak_sl_harga = SL_PIPS * nilai_1_pip
    jarak_tp_harga = (SL_PIPS * RR_RATIO) * nilai_1_pip
    syarat_lebar_kotak_harga = MAKS_LEBAR_KOTAK_PIPS * nilai_1_pip
    jarak_be_harga = TARGET_BE_PIPS * nilai_1_pip  # Jarak untuk trigger BE

    posisi_aktif = [] 
    total_trade = hit_tp = hit_sl = hit_be = sinyal_diskip_berita = 0 
    
    waktu_awal_bt = df['time'].iloc[200].to_pydatetime().replace(tzinfo=timezone.utc)
    waktu_akhir_bt = df['time'].iloc[-1].to_pydatetime().replace(tzinfo=timezone.utc)
    jadwal_berita = muat_berita_high_impact(waktu_awal_bt, waktu_akhir_bt)
    
    for i in range(200, len(df)):
        candle_sekarang = df.iloc[i]
        
        # 1. CEK SL, TP, dan UPDATE BREAKEVEN
        posisi_selamat = [] 
        for posisi in posisi_aktif:
            posisi_ditutup = False
            
            # --- CEK PENUTUPAN POSISI ---
            if posisi['tipe'] == "BUY":
                if candle_sekarang['low'] <= posisi['sl']: 
                    if posisi['is_be']: hit_be += 1
                    else: hit_sl += 1
                    posisi_ditutup = True
                elif candle_sekarang['high'] >= posisi['tp']: 
                    hit_tp += 1
                    posisi_ditutup = True
            elif posisi['tipe'] == "SELL":
                if candle_sekarang['high'] >= posisi['sl']: 
                    if posisi['is_be']: hit_be += 1
                    else: hit_sl += 1
                    posisi_ditutup = True
                elif candle_sekarang['low'] <= posisi['tp']: 
                    hit_tp += 1
                    posisi_ditutup = True
            
            # --- CEK TRIGGER BREAKEVEN JIKA POSISI MASIH AKTIF ---
            if not posisi_ditutup:
                if GUNAKAN_BE and not posisi['is_be']:
                    if posisi['tipe'] == "BUY" and candle_sekarang['high'] >= (posisi['entry'] + jarak_be_harga):
                        posisi['sl'] = posisi['entry'] # Geser SL ke harga Entry
                        posisi['is_be'] = True         # Tandai posisi sudah aman
                    elif posisi['tipe'] == "SELL" and candle_sekarang['low'] <= (posisi['entry'] - jarak_be_harga):
                        posisi['sl'] = posisi['entry'] # Geser SL ke harga Entry
                        posisi['is_be'] = True         # Tandai posisi sudah aman
                
                posisi_selamat.append(posisi) 
                
        posisi_aktif = posisi_selamat 
        
        # 2. CARI SINYAL BARU
        if len(posisi_aktif) < MAKSIMAL_POSISI:
            c_valid = df.iloc[i-1]
            lebar_kotak_aktual = c_valid['Box_High'] - c_valid['Box_Low']
            kotak_valid = lebar_kotak_aktual <= syarat_lebar_kotak_harga
            
            breakout_buy = c_valid['close'] > c_valid['Box_High']
            breakout_sell = c_valid['close'] < c_valid['Box_Low']
            
            waktu_candle = candle_sekarang['time'].replace(tzinfo=timezone.utc)
            sedang_news = len(jadwal_berita) > 0 and cek_zona_berita(waktu_candle, jadwal_berita, JEDA_BERITA_MENIT)
            
            if (c_valid['close'] > c_valid['EMA_200']) and kotak_valid and breakout_buy:
                if sedang_news: sinyal_diskip_berita += 1
                else:
                    harga_entry = candle_sekarang['open']
                    posisi_aktif.append({'tipe': 'BUY', 'entry': harga_entry, 'sl': harga_entry - jarak_sl_harga, 'tp': harga_entry + jarak_tp_harga, 'is_be': False})
                    total_trade += 1
                
            elif (c_valid['close'] < c_valid['EMA_200']) and kotak_valid and breakout_sell:
                if sedang_news: sinyal_diskip_berita += 1
                else:
                    harga_entry = candle_sekarang['open']
                    posisi_aktif.append({'tipe': 'SELL', 'entry': harga_entry, 'sl': harga_entry + jarak_sl_harga, 'tp': harga_entry - jarak_tp_harga, 'is_be': False})
                    total_trade += 1

    # ==========================================
    # 4. HASIL LAPORAN
    # ==========================================
    winrate = (hit_tp / total_trade) * 100 if total_trade > 0 else 0
    safe_rate = ((hit_tp + hit_be) / total_trade) * 100 if total_trade > 0 else 0

    print("="*45)
    print("🛡️ HASIL BACKTEST BREAKOUT + BREAKEVEN")
    print("="*45)
    print(f"Total Trade        : {total_trade} Posisi")
    print(f"🟢 Menang (TP)     : {hit_tp} Kali (+$6.00)")
    print(f"🟡 Selamat (BE)    : {hit_be} Kali ($0.00)")
    print(f"🔴 Kalah (SL)      : {hit_sl} Kali (-$3.00)")
    print("-"*45)
    print(f"Winrate Murni      : {winrate:.2f} % (Hanya TP)")
    print(f"Safe Rate (Aman)   : {safe_rate:.2f} % (TP + BE)")
    print("="*45)
    
    mt5.shutdown()

if __name__ == "__main__":
    mulai_backtest()