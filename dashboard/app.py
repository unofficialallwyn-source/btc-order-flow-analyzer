"""Streamlit BTC live chart. No authenticated endpoints, order placement, or storage required."""
import time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import httpx
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from analytics import delta_bars,footprint,book_imbalance,classify_spike
from live_feed import LiveFeed
from flow_interpretation import interpret_trade_window

API="https://api.india.delta.exchange/v2/history/candles"
IST=ZoneInfo("Asia/Kolkata")

def ist_label(ts):
    return datetime.fromtimestamp(float(ts),timezone.utc).astimezone(IST).strftime("%Y-%m-%d %I:%M:%S %p IST")

def ist_plot(series):
    return pd.to_datetime(series,unit="s",utc=True).dt.tz_convert(IST).dt.tz_localize(None)

st.set_page_config(page_title="BTC Order Flow",page_icon="📈",layout="wide")
st.title("BTCUSD · Live Order Flow")
st.caption("Delta Exchange India public market feed | read-only | live CVD begins when this dashboard connects | All displayed times are IST")

@st.cache_resource
def feed():
    return LiveFeed()

@st.cache_data(ttl=20,show_spinner=False)
def history(interval,lookback):
    end=int(time.time())
    start=end-lookback*int(interval[:-1])*({"m":60,"h":3600}[interval[-1]])
    with httpx.Client(timeout=12) as client:
        r=client.get(API,params={"symbol":"BTCUSD","resolution":interval,"start":start,"end":end})
        r.raise_for_status()
        response=r.json()
    if not isinstance(response.get("result"),list):
        raise ValueError(f"Delta candle API returned no data: {response}")
    data=sorted(response["result"],key=lambda x:x["time"])
    # Exclude still-forming candles from signal detector (and keep them on the display).
    return data

sidebar=st.sidebar
sidebar.header("Settings")
resolution=sidebar.selectbox("Candle interval",["1m","5m","15m","1h"],index=2)
lookback=sidebar.slider("Candles on chart",50,500,160,step=10)
refresh=sidebar.slider("Refresh every (seconds)",2,30,5)
window=sidebar.slider("Trade tape window (minutes)",5,120,30,step=5)
step=sidebar.selectbox("Footprint price bin ($)",[0.5,1.0,2.5,5.0,10.0,25.0],index=3)
st_autorefresh(interval=refresh*1000,key="live_refresh")

live=feed().snapshot(seconds=window*60)
try:
    candles=history(resolution,lookback)
except (httpx.HTTPError,ValueError) as exc:
    candles=[]
    st.error(f"Historical candle request failed: {exc}")
if live["status"]!="connected":
    st.warning(f"Trade feed: {live['status']}. CVD and footprint may be incomplete.")
if live["latest_trade_at"] and time.time()-live["latest_trade_at"]>30:
    st.warning("Trade feed is stale (>30 seconds since the last trade). Do not interpret these metrics as live.")
if live["disconnections"]:
    st.info(f"Feed has reconnected {live['disconnections']} times. CVD is session-only and may contain gaps.")

trades=live["trades"]
flows=delta_bars(trades)
last=trades[-1]["price"] if trades else (candles[-1]["close"] if candles else None)
delta=sum(x["delta"] for x in flows)
vol=sum(t["size"] for t in trades)
book=live["book"]
imb=book_imbalance(book)
m1,m2,m3,m4=st.columns(4)
m1.metric("BTCUSD last trade",f"${last:,.1f}" if last is not None else "—")
m2.metric("Window trade volume",f"{vol:,.0f} contracts")
m3.metric("Window net delta",f"{delta:+,.0f} contracts")
m4.metric("Top 10 book imbalance",f"{imb:+.1%}" if imb is not None else "—")
st.caption(f"Source status: {live['status']} | tape window {window}m | book snapshot may change; resting size is not executed volume")

st.subheader("Live Order-Flow Interpretation")
reading=interpret_trade_window(trades)
if live["status"]!="connected" or not live["latest_trade_at"] or time.time()-live["latest_trade_at"]>30 or live["disconnections"]:
    st.warning("Interpretation may contain gaps or stale trades; absorption is a hypothesis, not proof.")
if reading["state"]=="insufficient":
    st.info(reading["message"])
else:
    st.metric("Price change in selected trade window",f"{reading['price_change_pct']:+.3f}%")
    if reading["state"] in ("selling_pressure","seller_absorption"):
        st.error(f"**{reading['title']}** — {reading['message']}")
    else:
        st.success(f"**{reading['title']}** — {reading['message']}")
    st.caption(f"Tape from {ist_label(trades[0]['timestamp'])} to {ist_label(trades[-1]['timestamp'])}.")
with st.expander("Interpretation guide"):
    st.markdown("""1. **Negative delta + falling price:** Selling aggression is moving price lower.
2. **Negative delta + stable or rising price:** Buyers may be absorbing sell orders.
3. **Positive delta + rising price:** Buying aggression is moving price higher.
4. **Positive delta + falling or stagnant price:** Sellers may be absorbing buy orders.""")

if candles:
    frame=pd.DataFrame(candles)
    frame["dt"]=ist_plot(frame["time"])
    chart=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.04,
                        row_heights=[.77,.23])
    chart.add_trace(go.Candlestick(x=frame["dt"],open=frame["open"],high=frame["high"],
                                  low=frame["low"],close=frame["close"],name="BTCUSD"),row=1,col=1)
    colors=["#24a785" if c>=o else "#e15e65" for o,c in zip(frame["open"],frame["close"])]
    chart.add_trace(go.Bar(x=frame["dt"],y=frame["volume"],name="Candle volume",
                           marker_color=colors),row=2,col=1)
    chart.update_layout(height=580,xaxis_rangeslider_visible=False,margin=dict(l=10,r=10,t=20,b=5),
                        template="plotly_dark",showlegend=False)
    st.plotly_chart(chart,use_container_width=True)
    # UTC candlesticks; do not treat current unfinished candle as confirmed.
    seconds=int(resolution[:-1])*({"m":60,"h":3600}[resolution[-1]])
    complete=[c for c in candles if c["time"]+seconds<=int(time.time())]
    if resolution=="15m":
        signals=classify_spike(complete)
        st.subheader("Confirmed 15m volume-spike reversals")
        if signals:
            signal_df=pd.DataFrame(signals[-12:])
            for col in ("time","confirmed"):
                signal_df[col]=signal_df[col].map(ist_label)
            st.dataframe(signal_df.rename(columns={"time":"Time (IST)","confirmed":"Confirmed (IST)"}),use_container_width=True,hide_index=True)
        else:
            st.write("No confirmed signals in the selected sample.")
    else:
        st.caption("Select 15m to see volume-spike reversal signals.")

left,right=st.columns(2)
with left:
    st.subheader("True aggressor CVD (session only)")
    if flows:
        f=pd.DataFrame(flows)
        f["time_ist"]=pd.to_datetime(f["time"],utc=True).dt.tz_convert(IST).dt.tz_localize(None)
        cvdfig=go.Figure(go.Scatter(x=f["time_ist"],y=f["cvd"],mode="lines",name="CVD"))
        cvdfig.update_layout(template="plotly_dark",height=260,margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(cvdfig,use_container_width=True)
        flow_table=f[["time_ist","buy","sell","delta"]].tail(12).copy()
        flow_table["time_ist"]=flow_table["time_ist"].dt.strftime("%Y-%m-%d %I:%M:%S %p IST")
        st.dataframe(flow_table.rename(columns={"time_ist":"Time (IST)"}),hide_index=True,use_container_width=True)
    else:
        st.info("Waiting for public trades. Historical exchange CVD is not available from OHLCV.")
with right:
    st.subheader("Price-level footprint · current 15m interval")
    rows=footprint(trades,price_step=step)
    if rows:
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,height=310)
    else:
        st.info("No trades in the current 15m bucket within the selected tape window.")

st.subheader("Top-of-book snapshot (not historical liquidity)")
if book:
    b,a=st.columns(2)
    with b:
        st.write("Bids")
        st.dataframe(pd.DataFrame(book["bids"][:15],columns=["Price","Contracts"]),hide_index=True,use_container_width=True)
    with a:
        st.write("Asks")
        st.dataframe(pd.DataFrame(book["asks"][:15],columns=["Price","Contracts"]),hide_index=True,use_container_width=True)
    st.caption(f"Exchange book timestamp: {ist_label(book["timestamp"])}")
else:
    st.info("Waiting for order-book snapshot.")
st.caption("Not investment advice. Feed gaps and partial sessions make CVD unsuitable for unqualified historical comparisons. No trade execution functionality.")
