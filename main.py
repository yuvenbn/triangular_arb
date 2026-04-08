import asyncio
import os
import requests
import time

# allow minimal octobot_commons imports
os.environ["USE_MINIMAL_LIBS"] = "true"

import octobot_commons.symbols as symbols
import octobot_commons.os_util as os_util
import triangular_arbitrage.detector as detector

# 🔑 Telegram bot token and chat ID
TOKEN = "8347506046:AAFLvNFmtW-FxVrataZa-MHdGFfGm_mabW4"
CHAT_ID = "2063564998"

# Interval between scans in seconds
SCAN_INTERVAL = 60  # 1 minute

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message
        })
        print('Telegram alert sent ✅')
    except Exception as e:
        print("Telegram error:", e)

def get_order_side(opportunity: detector.ShortTicker):
    return 'buy' if opportunity.reversed else 'sell'

async def scan_loop():
    exchange_name = "bitget"

    while True:
        print("\nScanning for opportunities...")
        try:
            best_opportunities, best_profit = await detector.run_detection(exchange_name, max_cycle=3)

            if best_opportunities is not None:
                total_profit_percentage = round((best_profit - 1) * 100, 5)

                print("-------------------------------------------")
                print(f"New {total_profit_percentage}% {exchange_name} opportunity:")

                message = f"🔥 {exchange_name.upper()} Arbitrage Opportunity\n"
                message += f"Profit: {total_profit_percentage}%\n\n"

                for i, opportunity in enumerate(best_opportunities):
                    base_currency = opportunity.symbol.base
                    quote_currency = opportunity.symbol.quote
                    order_side = get_order_side(opportunity)

                    line = (
                        f"{i + 1}. {order_side} {base_currency} "
                        f"{'with' if order_side == 'buy' else 'for'} "
                        f"{quote_currency} @ {opportunity.last_price:.6f}"
                    )

                    print(line)
                    message += line + "\n"

                print("-------------------------------------------")

                # Only send meaningful alerts
                if total_profit_percentage > 0.3:
                    send_telegram(message)

            else:
                print("No opportunity detected")

        except Exception as e:
            print("Error during scan:", e)

        # Wait before next scan
        await asyncio.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("🚀 Starting continuous arbitrage scanner...")
    asyncio.run(scan_loop())