import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
import json
import os
import time

# --- Telegram настройки ---
TELEGRAM_TOKEN = "8070255262:AAEzecDs3VIvIpG4_-8A9I1iaz3N9tEJX5w"
CHAT_ID = "396459350"

# --- Файл истории ---
HISTORY_FILE = "history.json"

# --- Streamlit настройки ---
st.set_page_config(page_title="Gate.io vs DEX Spread Monitor", layout="wide")
st.title("📊 Мониторинг спреда: Gate.io vs DEX")
st.sidebar.header("🔧 Настройки")

# --- Настройки пользователя ---
future_symbol = st.sidebar.text_input("Gate.io фьючерс", "BOOM_USDT")
contract_address = st.sidebar.text_input("Контракт токена (BNB)", "0xcE7C3B5E058C196a0EAAa21F8E4BF8C2C07C2935")
spread_up = st.sidebar.number_input("🔺 Спред вверх (%)", value=2.0)
spread_down = st.sidebar.number_input("🔻 Спред вниз (%)", value=-2.0)

# --- Загрузка истории ---
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        st.session_state.history = json.load(f)
else:
    st.session_state.history = {
        "time": [], "cex": [], "dex": [], "spread": [], "dex_name": [], "dex_link": []
    }

# --- Получение цены с Gate.io ---
def get_gate_price(symbol):
    try:
        url = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
        res = requests.get(url, timeout=10).json()
        for item in res:
            if item["contract"].lower() == symbol.lower():
                return float(item["last"])
    except Exception as e:
        print("Gate.io error:", e)
    return None

# --- Получение цены с Dexscreener ---
def get_dex_price(contract):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={contract}"
        res = requests.get(url, timeout=10).json()

        best = None
        max_liquidity = 0

        for pair in res["pairs"]:
            if not pair.get("priceUsd"):
                continue
            liquidity = float(pair["liquidity"]["usd"])
            if liquidity > max_liquidity:
                max_liquidity = liquidity
                best = pair

        if best:
            return float(best["priceUsd"]), best["dexId"], best["url"], max_liquidity
    except Exception as e:
        print("Dexscreener error:", e)
    return None, None, None, None

# --- Telegram уведомление ---
def send_telegram_alert(spread, token, dex_name, dex_link, gate_symbol, liquidity):
    message = (
        f"📣 *Арбитраж обнаружен*\n"
        f"*Токен:* `{token}` ({dex_name})\n"
        f"📊 *Спред:* `{spread:.2f}%`\n"
        f"💧 *Ликвидность:* `${liquidity:,.0f}`\n"
        f"🟢 [DEX (Dexscreener)]({dex_link})\n"
        f"🔵 [Фьючерс Gate.io](https://www.gate.io/futures_trade/{gate_symbol})"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=data)
        print("Telegram:", response.status_code, response.text)
    except Exception as e:
        print("Telegram error:", e)

# --- Основной поток ---
placeholder = st.empty()
last_alert_time = 0

while True:
    now = datetime.now().strftime("%H:%M:%S")

    cex_price = get_gate_price(future_symbol)
    dex_price, dex_name, dex_link, liquidity = get_dex_price(contract_address)

    with placeholder.container():
        if cex_price and dex_price:
            spread = (cex_price - dex_price) / dex_price * 100

            # --- История ---
            st.session_state.history["time"].append(now)
            st.session_state.history["cex"].append(cex_price)
            st.session_state.history["dex"].append(dex_price)
            st.session_state.history["spread"].append(spread)
            st.session_state.history["dex_name"].append(dex_name)
            st.session_state.history["dex_link"].append(dex_link)

            with open(HISTORY_FILE, "w") as f:
                json.dump(st.session_state.history, f)

            # --- Метрики ---
            col1, col2, col3 = st.columns(3)
            col1.metric("📉 Gate.io", f"{cex_price:.6f} USDT")
            col2.metric(f"🥞 {dex_name}", f"{dex_price:.6f} USDT")
            col3.metric("📊 Спред", f"{spread:.2f}%")

            # --- Данные для графика ---
            df = pd.DataFrame({
                "Время": st.session_state.history["time"],
                "Gate.io": st.session_state.history["cex"],
                "DEX": st.session_state.history["dex"],
                "Спред (%)": st.session_state.history["spread"]
            })

            if not df.empty:
                max_spread = df["Спред (%)"].max()
                min_spread = df["Спред (%)"].min()
                max_spread_time = df[df["Спред (%)"] == max_spread]["Время"].values[0]
                min_spread_time = df[df["Спред (%)"] == min_spread]["Время"].values[0]

                col4, col5 = st.columns(2)
                col4.metric("📈 Макс. спред", f"{max_spread:.2f}%", help=f"Время: {max_spread_time}")
                col5.metric("📉 Мин. спред", f"{min_spread:.2f}%", help=f"Время: {min_spread_time}")

            # --- График ---
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["Время"], y=df["Gate.io"], name="Gate.io", line=dict(color="blue")))
            fig.add_trace(go.Scatter(x=df["Время"], y=df["DEX"], name="DEX", line=dict(color="green")))
            fig.add_trace(go.Scatter(x=df["Время"], y=df["Спред (%)"], name="Спред (%)",
                                     line=dict(color="red", dash="dot"), yaxis="y2"))

            fig.update_layout(
                xaxis=dict(
                    title="Время",
                    rangeslider=dict(visible=True),
                    rangeselector=dict(
                        buttons=list([
                            dict(count=10, label="10 мин", step="minute", stepmode="backward"),
                            dict(count=30, label="30 мин", step="minute", stepmode="backward"),
                            dict(step="all", label="Всё")
                        ])
                    )
                ),
                yaxis=dict(title="Цена USDT"),
                yaxis2=dict(title="Спред %", overlaying="y", side="right"),
                hovermode="x unified",
                legend=dict(x=0, y=1.1, orientation="h"),
                height=600
            )

            st.plotly_chart(fig, use_container_width=True)
            st.markdown(f"[🔗 DexScreener]({dex_link})")

            # --- Уведомление ---
            if (spread >= spread_up or spread <= spread_down) and (time.time() - last_alert_time > 300):
                send_telegram_alert(spread, future_symbol, dex_name, dex_link, future_symbol, liquidity)
                last_alert_time = time.time()

        else:
            st.warning("❌ Не удалось получить цену с Gate.io или DEX")

    time.sleep(10)
