from binance.cm_futures import CMFutures
from binance.spot import Spot
from binance.lib.enums import TransferType
from datetime import datetime, date
import requests
import math
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
import os

load_dotenv(override=True)


cm_futures_client = CMFutures(key=os.getenv("API_KEY"), secret=os.getenv("SECRET_KEY"), show_limit_usage=True)
spot_client = Spot(api_key=os.getenv("API_KEY"), api_secret=os.getenv("SECRET_KEY"))
api_key = os.getenv("API_KEY")
headers = {"X-MBX-APIKEY": api_key}

def open_cm_futures_sintetic(pair_symbol, usd_to_invest):

    # API key/secret are required for user data endpoints
    print(cm_futures_client.time())
    print(spot_client.time())
    pair = pair_symbol.split("_")[0]
    pairs_position_risk = cm_futures_client.get_position_risk(pair=pair)['data']
    pair_position_risk = next((item for item in pairs_position_risk if item["symbol"] == pair_symbol), None)

    if pair_position_risk["leverage"] != "1":
        cm_futures_client.change_leverage(pair_symbol, 1)
    if pair_position_risk["marginType"] != "isolated":
        cm_futures_client.change_margin_type(pair_symbol, "ISOLATED")

    all_cm_pairs = cm_futures_client.exchange_info()["data"]["symbols"]
    # cm_delivery_pairs = [d for d in all_cm_pairs if "PERPETUAL" not in d.get("contractType")]
    for cm_pair in all_cm_pairs:
        if cm_pair["symbol"] == pair_symbol:
            pair_info = cm_pair
            break

    spot_symbol = pair_info["baseAsset"]+"USDT"
    usd_per_cont = pair_info["contractSize"]
    conts_to_short = math.floor(usd_to_invest / usd_per_cont)
    bids_depth = cm_futures_client.depth(pair_symbol)["data"]["bids"]
    # mark_price = float(cm_futures_client.mark_price(pair_symbol)["data"][0]["markPrice"])
    avg_short_price = get_avarage_short_price(bids_depth, conts_to_short)
    spot_price = float(spot_client.ticker_price(spot_symbol)["price"])
    
    coins_needed = float(Decimal(conts_to_short*usd_per_cont*1.015/avg_short_price + 0.0001).quantize(Decimal("0.0000"), rounding=ROUND_DOWN)) 
    usdt_needed = round(coins_needed * spot_price, 2)
    available_spot_usdt = float(spot_client.user_asset(asset = "USDT")[0]["free"])
    
    
    if available_spot_usdt > usdt_needed:
        
        ## api ##
        # buy coins_needed in spot.
        # print(f'Starting process to open short position {pair_symbol} with conts = {conts_to_short} aprox usd = {usdt_needed}')
        # buy_order = spot_client.new_order(spot_symbol, "BUY", "MARKET", quoteOrderQty=usdt_needed)
        # qty_bought = buy_order["executedQty"]

        ## manual ##
        available_spot_coin_start = float(spot_client.user_asset(asset = pair_info["baseAsset"])[0]["free"])
        print(f'buy {usdt_needed} USDT of {spot_symbol} on spot')
        input("Press any key after buying to continue:")
        available_spot_coin_end = float(spot_client.user_asset(asset = pair_info["baseAsset"])[0]["free"])
        qty_bought = str(first_7_decimals_no_rounding(available_spot_coin_end - available_spot_coin_start))

        # transfer bought coins to MAIN_CMFUTURE
        spot_to_cm_transfer = spot_client.user_universal_transfer("MAIN_CMFUTURE", pair_info["baseAsset"], qty_bought)
        cm_futures_balances = cm_futures_client.balance(asset=pair_info["baseAsset"])["data"]
        coin_future_balance = next((balance for balance in cm_futures_balances if balance["asset"] == pair_info["baseAsset"]), None)["availableBalance"]
        if coin_future_balance >= qty_bought:
            # open short cm future
            short_order = cm_futures_client.new_order(pair_symbol, "SELL", "MARKET", quantity = conts_to_short)
            send_telegram_notification(
f'''short_order {pair_symbol} with usdt = {usd_to_invest}
bought {pair_info['baseAsset']} = {qty_bought} for {usdt_needed} usdt.
shorted conts = {conts_to_short} with position {usd_per_cont/avg_short_price*conts_to_short} and mark price {avg_short_price}
{float(qty_bought) - (usd_per_cont/avg_short_price*conts_to_short)} {pair_symbol} exess bough''')
            return conts_to_short
        else:
            print(f"Coin future balance is {coin_future_balance}, but we bought {qty_bought} on spot.")
    else:
        print(f"No enough USDT, needed {usdt_needed}, but got {available_spot_usdt} available on spot.")


def close_cm_futures_sintetic(pair_symbol, sell_in_spot: bool = True, api: bool = True):

    # API key/secret are required for user data endpoints
    print(cm_futures_client.time())
    print(spot_client.time())
    pair = pair_symbol.split("_")[0]
    base_asset = pair.split('USD')[0]
    spot_exchange_info = spot_client.exchange_info()
    
    spot_exchange_symbols_data = spot_exchange_info["symbols"]
    spot_symbol = base_asset+"USDT"
    spot_symbol_data = next((item for item in spot_exchange_symbols_data if item["symbol"] == spot_symbol), None)["filters"]
    spot_symbol_data_step_size = float(next((item for item in spot_symbol_data if item["filterType"] == 'LOT_SIZE'), None)["stepSize"])
    account_data = cm_futures_client.account()['data']
    initial_coin_balance = float(next((item for item in account_data["assets"] if item["asset"] == base_asset), None)['availableBalance'])
    current_positions = account_data['positions']
    position_to_close = next((item for item in current_positions if item["symbol"] == pair_symbol), None)
    cont_amount_to_close = abs(int(position_to_close['positionAmt']))
    print(f'Trying to close position {pair_symbol} with conts = {cont_amount_to_close}')
    closed_position = cm_futures_client.new_order(pair_symbol, "BUY", "MARKET", quantity = cont_amount_to_close)
    print(f'closed_position = {closed_position}')

    account_data = cm_futures_client.account()['data']
    coin_balance_after_colsing = float(next((item for item in account_data["assets"] if item["asset"] == base_asset), None)['availableBalance'])
    
    coins_to_sell = adjust_qty_to_step_size(coin_balance_after_colsing - initial_coin_balance, spot_symbol_data_step_size)
    if sell_in_spot:
        cm_to_spot_transfer = spot_client.user_universal_transfer("CMFUTURE_MAIN", base_asset, coins_to_sell)
        print(f'cm_to_spot_transfer = {cm_to_spot_transfer}')
        
        if api:
            sell_coint_on_spot = spot_client.new_order(spot_symbol, "SELL", "MARKET", quantity=coins_to_sell)
            print(f'sell_coint_on_spot = {sell_coint_on_spot}')
        else:
            ## manual ##
            print(f'Sell {coins_to_sell} {base_asset} on {spot_symbol} on spot')
            input("Press any key after selling to continue:")

    send_telegram_notification(
f'''Closed {cont_amount_to_close} conts for short position {pair_symbol} 
initial {base_asset} balance in cm wallet {initial_coin_balance}
{base_asset} balance after closing position in cm wallet {coin_balance_after_colsing}
{base_asset} to sell in spot: {coins_to_sell}''')


def get_futures_rates(my_positions):
    all_cm_pairs = cm_futures_client.exchange_info()["data"]["symbols"]
    all_rates = []
    limit_ussage = 0
    cm_delivery_pairs = [d for d in all_cm_pairs if "PERPETUAL" not in d.get("contractType")]
    all_mark_prices, limit_ussage = mark_price_requests()
    all_mark_prices_devilery = [d for d in all_mark_prices if "PERP" not in d.get("symbol")]
    
    for pair_mark_price in all_mark_prices_devilery:
        pair_info = next((item for item in cm_delivery_pairs if item["symbol"] == pair_mark_price["symbol"]), None)
        if pair_info:
            future_dte = abs((date.today() - date.fromtimestamp(int(pair_info["deliveryDate"]/1000))).days)
            # mark_price2 = float(pair_mark_price["markPrice"])
            depths = cm_futures_client.depth(pair_info["symbol"])["data"]
            bids_depth = depths["bids"]
            asks_depth = depths["asks"]
            usd_per_cont = pair_info["contractSize"]
            conts_to_short = 1000 / usd_per_cont
            mark_price = get_avarage_short_price(bids_depth, conts_to_short)
            if pair_info["symbol"] in my_positions.keys():
                conts_to_short = my_positions[pair_info["symbol"]]["conts"]
            mark_price_close = get_avarage_short_price(asks_depth, conts_to_short)
            index_price = float(pair_mark_price["indexPrice"])
            anual_rate = calculate_annual_rate(mark_price, index_price, future_dte)
            anual_rate_close = calculate_annual_rate(mark_price_close, index_price, future_dte)
            all_rates.append({"symbol": pair_info["symbol"], "annual_rate %": str(anual_rate), "close_rate": str(anual_rate_close), "dte": future_dte, "data": {"mark_price": mark_price, "index_price": index_price}})
    return all_rates, limit_ussage

        
def calculate_annual_rate(mark_price, index_price, dte):
    if dte <= 0:
        return 0  # Avoid division by zero
    basis = (mark_price - index_price) / index_price
    annual_rate = basis * (365 / dte) * 100
    return round(annual_rate, 2)


def mark_price_requests():
    url = "https://dapi.binance.com//dapi/v1/premiumIndex"

    response = requests.get(url, headers=headers)
    return response.json(), response.headers.get("X-MBX-USED-WEIGHT-1M")

def adjust_qty_to_step_size(qty, step_size):
    precision = abs(math.log10(step_size))  # Determine decimal places
    adjusted_qty = math.floor(qty / step_size) * step_size
    return round(adjusted_qty, int(precision))  # Round to correct precision

def get_avarage_short_price(depth, conts_to_short):
    conts_sum = 0
    price_sum = 0
    for bid in depth:
        price, conts =  bid
        conts_sum += float(conts)
        price_sum += float(price)*float(conts)
        if conts_sum >= conts_to_short:
            break
    return price_sum/conts_sum 

def send_telegram_notification(message: str):
    requests.post(
        f"https://api.telegram.org/{os.getenv('TELEGRAM_BOT_ID')}/sendMessage?chat_id={os.getenv('TELEGRAM_CHAT_ID')}&text={message}")
    

def first_7_decimals_no_rounding(num):
    num_str = f"{num:.15f}"  # ensure enough precision
    if '.' in num_str:
        whole, decimal = num_str.split('.')
        return float(f"{whole}.{decimal[:7]}")
    return float(num_str)  # in case it's an int