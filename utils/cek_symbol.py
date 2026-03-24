import MetaTrader5 as mt5

if mt5.initialize():
    symbol = "XAUUSDm"
    info = mt5.symbol_info(symbol)
    if info:
        print(f"Symbol: {symbol}")
        print(f"Digits: {info.digits}")
        print(f"Point: {info.point}")
        
        # Test perhitungan SL
        for sl_pips in [20, 50, 100]:
            pengali = 10 if info.digits in [3, 5] else 1
            jarak = sl_pips * pengali * info.point
            print(f"SL {sl_pips} Pips = {jarak} poin (dalam harga)")
    else:
        print(f"Symbol {symbol} tidak ditemukan")
    mt5.shutdown()
