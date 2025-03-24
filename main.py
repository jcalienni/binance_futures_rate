import requests
import json
from datetime import datetime
from time import sleep
import os
from binance_api import open_cm_futures_sintetic, get_futures_rates
from dotenv import load_dotenv
import os

load_dotenv()

RATE_TO_NOTIFY = 10

def main():
    while True:
        try:
            with open("position.json", 'r') as f:
                my_positions = json.loads(f.read())
            current_data, rate = get_futures_rates(my_positions)
            historical = {}
            historical[datetime.now().strftime("%d/%m/%Y - %H:%M")] = current_data
            filename = f'{datetime.now().strftime("%d-%m-%Y")}.json'
            # Check if the file exists
            if os.path.exists(filename):
                # Read the existing data
                with open(filename, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}
            else:
                data = {}


            if len(data) == 0:
                data.update(historical)
            else:
                data.update(historical)
            check_my_positions(current_data, my_positions)

            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f'saved data for {datetime.now().strftime("%d/%m/%Y - %H:%M")}. Rate used: {rate}')
            sleep(20)
        except:
            print(f'Error happened')
            sleep(60)

def check_my_positions(current_data, my_positions):
    for curent_dict in current_data:
        current_symbol = curent_dict["symbol"]
        current_close_rate = curent_dict["close_rate"]
        current_open_rate = curent_dict["annual_rate %"]
        current_dte = curent_dict["dte"]
        for my_symbol, position_info in my_positions.items():
            if current_symbol == my_symbol:
                if float(current_close_rate) <= 0:
                    send_telegram_notification(f'EXELENT rate to close position {my_symbol}, current rate is {current_close_rate} vs my {position_info["open_rate"]}')
                elif float(current_close_rate) <= 3:
                    send_telegram_notification(f'Good rate to close position {my_symbol}, current rate is {current_close_rate} vs my {position_info["open_rate"]}')
                break
                
        if current_symbol not in my_positions.keys() and float(current_open_rate) >= RATE_TO_NOTIFY and current_dte >= 30:
            check_good_trade_notification(current_symbol, float(current_open_rate))


def check_good_trade_notification(current_symbol, current_rate):
    with open('notifications.json', 'r') as f:
        data = json.load(f)
    last_date_notification = datetime.strptime(data[current_symbol]["last_datetime"], "%d/%m/%Y - %H:%M")
    last_rate_notification = data[current_symbol]["last_rate"]
    if current_rate >= float(last_rate_notification):
        data[current_symbol]["last_datetime"] = datetime.now().strftime("%d/%m/%Y - %H:%M")
        data[current_symbol]["last_rate"] = current_rate
        send_telegram_notification(f'Good rate to open position {current_symbol}, current rate is {current_rate}')
        usd_to_invest = 200
        conts_shorted = 0
        # conts_shorted = open_cm_futures_sintetic(current_symbol, usd_to_invest)
        with open('position.json', 'r') as f:
            data_positions = json.load(f)
            data_positions[current_symbol] = {"open_rate": str(current_rate), "position_usd": usd_to_invest, "conts": conts_shorted}
        with open('position.json', 'w') as f:
            json.dump(data_positions, f)
        with open('notifications.json', 'w') as f:
            json.dump(data, f)



def send_telegram_notification(message: str):
    requests.post(
        f"https://api.telegram.org/{os.getenv('TELEGRAM_BOT_ID')}/sendMessage?chat_id={os.getenv('TELEGRAM_CHAT_ID')}&text={message}")

if __name__ == '__main__':
    main()