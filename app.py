import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import time
import uuid

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 스타일
# -----------------------------------------------------------------------------
st.set_page_config(page_title="SOXL Hunter V6", layout="wide")

# 스타일 설정 (박스 높이 고정 및 디자인)
st.markdown("""
<style>
    .signal-box {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        text-align: center;
        color: white;
        height: 180px; /* 박스 높이 고정 */
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .diamond { background-color: #6f42c1; border: 2px solid #fff; }
    .gold { background-color: #fd7e14; border: 2px solid #fff; }
    .silver { background-color: #004085; border: 2px solid #fff; }
    .hold { background-color: #495057; border: 1px dashed #ccc; } /* 회색 배경 */
    
    .big-font { font-size: 1.2rem; font-weight: bold; margin-bottom: 5px; }
    .desc-text { font-size: 0.9rem; opacity: 0.9; }
    .action-text { font-size: 1.1rem; font-weight: bold; margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.3); padding-top: 5px; }
    
    .ts-highlight { font-weight: 900; color: #d63384; background-color: #f8d7da; padding: 2px 6px; border-radius: 4px; }
    
    /* 탭 스타일 조정 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #f0f2f6; border-radius: 4px; padding: 10px; }
    .stTabs [aria-selected="true"] { background-color: #4e8cff; color: white; }
</style>
""", unsafe_allow_html=True)

check_years = 3

# -----------------------------------------------------------------------------
# 2. 데이터 가져오기
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_data(ticker="SOXL"):
    for attempt in range(5):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=f"{check_years}y", interval="1d")
            
            if df.empty or len(df) < 20:
                time.sleep(1)
                df = yf.download(ticker, period=f"{check_years}y", interval="1d", progress=False)

            if df.empty or len(df) < 20:
                time.sleep(2)
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA120'] = df['Close'].rolling(window=120).mean()
            df['MA200'] = df['Close'].rolling(window=200).mean()
            
            df['BB_Mid'] = df['MA20']
            df['BB_Std'] = df['Close'].rolling(window=20).std()
            df['BB_Lower'] = df['BB_Mid'] - (2 * df['BB_Std'])
            denom = (df['BB_Mid'] + (2 * df['BB_Std'])) - df['BB_Lower']
            df['Pct_B'] = np.where(denom == 0, 0, (df['Close'] - df['BB_Lower']) / denom)

            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            gain2 = (delta.where(delta > 0, 0)).rolling(window=2).mean()
            loss2 = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
            rs2 = gain2 / loss2
            df['RSI2'] = 100 - (100 / (1 + rs2))
            
            df['Return'] = df['Close'].pct_change()
            mean_20 = df['Return'].rolling(window=20).mean()
            std_20 = df['Return'].rolling(window=20).std()
            df['Sigma'] = (df['Return'] - mean_20) / std_20
            
            mean_60 = df['Return'].rolling(window=60).mean()
            std_60 = df['Return'].rolling(window=60).std()
            df['Sigma60'] = (df['Return'] - mean_60) / std_60
            
            df['VolMA20'] = df['Volume'].rolling(window=20).mean()
            df['Vol_Ratio'] = df['Volume'] / df['VolMA20']
            df['Is_Yangbong'] = df['Close'] > df['Open']
            
            return df
        except:
            time.sleep(1)
            continue
    return None

# -----------------------------------------------------------------------------
# 3. 지갑 및 포트폴리오 관리
# -----------------------------------------------------------------------------
WALLET_FILE = "my_wallet.json"
PORTFOLIO_FILE = "my_portfolio.json"

def load_json(file_path, default_data):
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            json.dump(default_data, f)
        return default_data
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except:
        return default_data

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f)

def load_wallet():
    return load_json(WALLET_FILE, {"hunter_cash": 700.0, "blitz_cash": 300.0})

def update_cash(strategy_type, amount, action):
    data = load_wallet()
    key = "blitz_cash" if strategy_type in ["Blitz", "블리츠"] else "hunter_cash"
    
    if action == "deposit": data[key] += amount
    elif action == "buy": data[key] -= amount
    elif action == "sell": data[key] += amount
    elif action == "set": data[key] = amount
        
    save_json(WALLET_FILE, data)
    return data

def load_portfolio():
    return load_json(PORTFOLIO_FILE, [])

def add_trade(date, tier, price, qty):
    data = load_portfolio()
    new_trade = {
        "id": str(uuid.uuid4()),
        "date": date.strftime("%Y-%m-%d"),
        "tier": tier,
        "price": float(price),
        "qty": int(qty),
        "status": "holding",
        "sell_price": 0.0,
        "sell_date": ""
    }
    data.append(new_trade)
    save_json(PORTFOLIO_FILE, data)

def delete_trade(trade_id):
    data = load_portfolio()
    data = [t for t in data if t["id"] != trade_id]
    save_json(PORTFOLIO_FILE, data)

def sell_trade(trade_id, sell_price):
    data = load_portfolio()
    sold_info = None
    for t in data:
        if t["id"] == trade_id and t["status"] == "holding":
            t["status"] = "sold"
            t["sell_price"] = float(sell_price)
            t["sell_date"] = datetime.now().strftime("%Y-%m-%d")
            sold_info = t
            break
            
    if sold_info:
        total = sold_info["sell_price"] * sold_info["qty"]
        w_type = "Blitz" if "블리츠" in sold_info["tier"] else "Hunter"
        update_cash(w_type, total, "sell")
        save_json(PORTFOLIO_FILE, data)
        return True, total, w_type
    return False, 0, ""

# -----------------------------------------------------------------------------
# 4. 메인 앱 구조
# -----------------------------------------------------------------------------
try:
    # [1. 메뉴 위치 수정] 사이드바 최상단으로 이동
    st.sidebar.title("🦅 Hunter V6 System")
    menu = st.sidebar.radio("📌 메뉴", ["🚀 SOXL 대시보드", "📜 과거 매매 기록", "📊 백테스트"])
    
    # 데이터 로드
    df = get_data("SOXL")
    if df is None or len(df) < 2:
        st.error("데이터 연결 실패. 잠시 후 다시 시도하세요.")
        st.stop()

    today = df.iloc[-1]
    prev = df.iloc[-2]
    current_price = today['Close']

    # --- 사이드바: 자산 관리 ---
    portfolio_data = load_portfolio()
    wallet = load_wallet()
    
    total_eval = sum([t['qty'] * current_price for t in portfolio_data if t['status'] == 'holding'])
    total_cash = wallet["hunter_cash"] + wallet["blitz_cash"]
    total_assets = total_eval + total_cash
    
    st.sidebar.markdown("---")
    st.sidebar.header("💰 내 자산 현황")
    st.sidebar.metric("🏆 총 자산 (평가+예수)", f"${total_assets:,.0f}")
    
    c1, c2 = st.sidebar.columns(2)
    c1.metric("🦅 Hunter", f"${wallet['hunter_cash']:,.0f}")
    c2.metric("⚡ Blitz", f"${wallet['blitz_cash']:,.0f}")
    
    # [3. 예수금 추가 기능 복구]
    with st.sidebar.expander("💵 예수금 입금/수정"):
        deposit_type = st.radio("계좌 선택", ["Hunter", "Blitz"])
        deposit_amount = st.number_input("입금액 ($)", step=100)
        if st.button("입금 확인"):
            update_cash(deposit_type, deposit_amount, "deposit")
            st.rerun()
            
    if st.sidebar.button("데이터/잔고 갱신"):
        st.cache_data.clear()
        st.rerun()

    # =========================================================================
    # [PAGE 1] 대시보드
    # =========================================================================
    if menu == "🚀 SOXL 대시보드":
        st.title("🦅 SOXL Hunter Dashboard")
        st.markdown("---")
        
        # 상단 정보
        chg = current_price - prev['Close']
        pct = (chg / prev['Close']) * 100
        color = "color: #ff4b4b;" if pct >= 0 else "color: #4b88ff;"
        sign = "+" if pct >= 0 else ""
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f"**현재가**<br><span style='font-size:24px; font-weight:bold;'>${current_price:.2f}</span> <span style='{color}'>({sign}{pct:.2f}%)</span>", unsafe_allow_html=True)
        with c2: st.markdown(f"**Sigma(20)**<br><span style='font-size:24px; font-weight:bold;'>{today['Sigma']:.2f}</span>", unsafe_allow_html=True)
        with c3: st.markdown(f"**RSI(14)**<br><span style='font-size:24px; font-weight:bold;'>{today['RSI']:.1f}</span>", unsafe_allow_html=True)
        with c4: st.markdown(f"**Volume**<br><span style='font-size:24px; font-weight:bold;'>{today['Vol_Ratio']:.2f}배</span>", unsafe_allow_html=True)

        # [2. 매수 신호 분석 디자인 수정] HTML 박스 형태로 복구
        st.markdown("---")
        st.subheader("📢 매수 신호 분석")
        
        sig, sig60 = today['Sigma'], today['Sigma60']
        rsi, vol = today['RSI'], today['Vol_Ratio']
        
        # 조건 로직
        is_dia = (sig <= -2.5) and (rsi < 30) and (vol >= 1.5)
        is_gold = ((sig <= -2.0) and (rsi < 30) and (vol >= 1.5)) or ((sig <= -1.8) and (sig60 <= -2.0))
        is_gold = is_gold and (not is_dia)
        cond_silver = (rsi < 45) and (today['Pct_B'] < 0.2)
        is_silver = cond_silver and today['Is_Yangbong']
        
        # 멘트 설정
        d_title = "💎 DIAMOND"
        d_cls = "diamond" if is_dia else "hold"
        d_msg = "조건 충족! 80% 매수" if is_dia else f"Sigma: {sig:.2f} (목표 -2.5)"
        
        g_title = "🥇 GOLD"
        g_cls = "gold" if is_gold else "hold"
        g_msg = "조건 충족! 50% 매수" if is_gold else f"Sigma: {sig:.2f} (목표 -2.0)"
        
        s_title = "🥈 SILVER"
        s_cls = "silver" if is_silver else "hold"
        s_msg = "양봉 확인됨! 20% 매수" if is_silver else ("양봉 대기중" if cond_silver else f"RSI: {rsi:.1f} (목표 45↓)")

        # HTML 출력
        c_d, c_g, c_s = st.columns(3)
        with c_d:
            st.markdown(f"""
            <div class="signal-box {d_cls}">
                <div class="big-font">{d_title}</div>
                <div class="desc-text">{d_msg}</div>
            </div>
            """, unsafe_allow_html=True)
        with c_g:
            st.markdown(f"""
            <div class="signal-box {g_cls}">
                <div class="big-font">{g_title}</div>
                <div class="desc-text">{g_msg}</div>
            </div>
            """, unsafe_allow_html=True)
        with c_s:
            st.markdown(f"""
            <div class="signal-box {s_cls}">
                <div class="big-font">{s_title}</div>
                <div class="desc-text">{s_msg}</div>
            </div>
            """, unsafe_allow_html=True)

        # 보유 자산 관리
        st.markdown("---")
        st.subheader("💼 현재 보유 자산")
        
        with st.expander("➕ 매수 기록 추가"):
            c1, c2, c3, c4 = st.columns(4)
            i_date = c1.date_input("날짜")
            i_tier = c2.selectbox("등급", ["💎 다이아", "🥇 골드", "🥈 실버", "⚡ 블리츠", "기타"])
            i_price = c3.number_input("단가", 0.0, step=0.01)
            i_qty = c4.number_input("수량", 1, step=1)
            if st.button("저장하기"):
                cost = i_price * i_qty
                w = "Blitz" if "블리츠" in i_tier else "Hunter"
                key = "blitz_cash" if w == "Blitz" else "hunter_cash"
                if wallet[key] >= cost:
                    update_cash(w, cost, "buy")
                    add_trade(i_date, i_tier, i_price, i_qty)
                    st.success("저장 완료")
                    st.rerun()
                else: st.error("잔고 부족")

        holdings = [t for t in portfolio_data if t['status'] == 'holding']
        if holdings:
            for t in holdings:
                ts_txt = "-"
                try:
                    peak = df.loc[df.index.strftime('%Y-%m-%d') >= t['date']]['Close'].max()
                    peak = max(peak, current_price) if not np.isnan(peak) else current_price
                    if "다이아" in t['tier']: stop = peak * 0.6
                    elif "골드" in t['tier']: stop = peak * 0.8
                    elif "실버" in t['tier']: stop = peak * 0.85
                    else: stop = t['price'] * 0.85
                    ts_txt = f"${stop:.2f}"
                except: pass

                profit = (current_price - t['price']) * t['qty']
                pct = (current_price - t['price']) / t['price'] * 100
                p_color = "red" if pct > 0 else "blue"

                with st.container(border=True):
                    cols = st.columns([1.5, 1.5, 1.5, 2, 2.5])
                    cols[0].markdown(f"**{t['date']}**\n\n{t['tier']}")
                    cols[1].markdown(f"평단: **${t['price']:.2f}**\n\n수량: **{t['qty']}**")
                    # [4. TS 강조 적용]
                    cols[2].markdown(f"현재: **${current_price:.2f}**\n\nTS: <span class='ts-highlight'>{ts_txt}</span>", unsafe_allow_html=True)
                    cols[3].markdown(f":{p_color}[**{pct:+.2f}%**]\n\n:{p_color}[**${profit:+.2f}**]")
                    
                    with cols[4]:
                        sell_price = st.number_input("매도가", value=float(current_price), key=f"p_{t['id']}", label_visibility="collapsed")
                        b1, b2 = st.columns(2)
                        if b1.button("매도", key=f"s_{t['id']}", type="primary"):
                            sell_trade(t['id'], sell_price)
                            st.rerun()
                        # [3. 삭제 버튼 빨간색 텍스트 스타일]
                        if b2.button("삭제", key=f"d_{t['id']}"):
                            delete_trade(t['id'])
                            st.rerun()
        else:
            st.info("보유 중인 자산이 없습니다.")

    # =========================================================================
    # [PAGE 2] 과거 매매 기록 (테이블 형식으로 간소화)
    # =========================================================================
    elif menu == "📜 과거 매매 기록":
        st.title("📜 매매 기록 일지")
        
        history = [t for t in portfolio_data if t['status'] == 'sold']
        
        # [4. 총 매매 횟수 왼쪽 정렬]
        st.markdown(f"### 총 매매 횟수: {len(history)}회")
        st.markdown("---")

        if history:
            data_list = []
            for t in history:
                profit = (t['sell_price'] - t['price']) * t['qty']
                pct = (t['sell_price'] - t['price']) / t['price'] * 100
                
                try:
                    d1 = datetime.strptime(t['date'], "%Y-%m-%d")
                    d2 = datetime.strptime(t['sell_date'], "%Y-%m-%d")
                    days = (d2 - d1).days
                except: days = 0

                data_list.append({
                    "등급": t['tier'],
                    "매수일": t['date'],
                    "매도일": t['sell_date'],
                    "보유": f"{days}일",
                    "매수단가": t['price'],
                    "매도단가": t['sell_price'],
                    "수량": t['qty'],
                    "수익금": profit,
                    "수익률": pct / 100 # 퍼센트 포맷을 위해 소수로 저장
                })
            
            df_hist = pd.DataFrame(data_list)
            
            # [4. 수익률 숫자와 색상만 표시]
            def color_surplus(val):
                color = 'red' if val > 0 else 'blue'
                return f'color: {color}; font-weight: bold;'

            st.dataframe(
                df_hist.style.format({
                    "매수단가": "${:.2f}",
                    "매도단가": "${:.2f}",
                    "수익금": "${:.2f}",
                    "수익률": "{:+.2f}%"
                }).map(color_surplus, subset=['수익률', '수익금']),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("기록이 없습니다.")

    # =========================================================================
    # [PAGE 3] 백테스트
    # =========================================================================
    elif menu == "📊 백테스트":
        st.title("📊 과거 수익률 분석")
        
        # 기존 백테스트 로직
        cond_dia = (df['Sigma'] <= -2.5) & (df['RSI'] < 30) & (df['Vol_Ratio'] >= 1.5)
        cond_gold_std = (df['Sigma'] <= -2.0) & (df['RSI'] < 30) & (df['Vol_Ratio'] >= 1.5)
        cond_gold_dual = (df['Sigma'] <= -1.8) & (df['Sigma60'] <= -2.0)
        cond_gold = (cond_gold_std | cond_gold_dual) & (~cond_dia)
        cond_silver = (df['RSI'] < 45) & (df['Pct_B'] < 0.2) & (df['Close'] > df['MA120']) & (df['Is_Yangbong']) & (~cond_dia) & (~cond_gold)
        cond_blitz = (df['RSI2'] < 5) & (df['Close'] > df['MA200'])

        history = []
        all_signals = sorted(list(set(np.where(cond_dia)[0]) | set(np.where(cond_gold)[0]) | set(np.where(cond_silver)[0]) | set(np.where(cond_blitz)[0])))

        for i in all_signals:
            if i < 200 or i >= len(df)-1: continue 
            date_str = df.index[i].strftime('%Y-%m-%d')
            price_buy = df['Close'].iloc[i]
            if cond_dia.iloc[i]: tier = "💎 다이아"
            elif cond_gold.iloc[i]: tier = "🥇 골드"
            elif cond_silver.iloc[i]: tier = "🥈 실버"
            elif cond_blitz.iloc[i]: tier = "⚡ 블리츠"
            else: tier = "기타"
            
            ret_5d = np.nan
            ret_15d = np.nan
            if i + 5 < len(df): ret_5d = ((df['Close'].iloc[i+5] - price_buy) / price_buy) * 100
            if i + 15 < len(df): ret_15d = ((df['Close'].iloc[i+15] - price_buy) / price_buy) * 100
            
            history.append({"날짜": date_str, "등급": tier, "매수가": price_buy, "수익률(5일)": ret_5d, "수익률(15일)": ret_15d})

        if history:
            df_hist = pd.DataFrame(history).sort_values("날짜", ascending=False)
            
            valid_5d = df_hist.dropna(subset=['수익률(5일)'])
            valid_15d = df_hist.dropna(subset=['수익률(15일)'])
            rate_5d = (valid_5d['수익률(5일)'] > 0).mean() * 100 if len(valid_5d) > 0 else 0
            rate_15d = (valid_15d['수익률(15일)'] > 0).mean() * 100 if len(valid_15d) > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            m1.metric("총 포착 신호", f"{len(df_hist)}회")
            m2.metric("5일 후 승률", f"{rate_5d:.1f}%")
            m3.metric("15일 후 승률", f"{rate_15d:.1f}%")
            
            st.markdown("---")
            
            def color_returns(val):
                if pd.isna(val): return ""
                color = '#ff4b4b' if val > 0 else '#4b88ff'
                return f'color: {color}; font-weight: bold;'

            st.dataframe(df_hist.style.format({"매수가": "${:.2f}", "수익률(5일)": "{:+.2f}%", "수익률(15일)": "{:+.2f}%"}, na_rep="-").map(color_returns, subset=['수익률(5일)', '수익률(15일)']), use_container_width=True, hide_index=True)
            
            csv = df_hist.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📊 전체 데이터 다운로드 (CSV)", csv, "soxl_backtest.csv", "text/csv")
        else:
            st.write("신호 없음")

except Exception as e:
    st.error(f"오류: {e}")





















