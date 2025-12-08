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
st.set_page_config(page_title="SOXL Hunter V6 Final Weapon", layout="wide")

# 스타일 설정
st.markdown("""
<style>
    .pyramid { background-color: #dc3545; border: 2px solid #ffc107; color: white; margin-top: 10px; }
    .big-font { font-size: 20px !important; font-weight: bold; }
    .signal-box { padding: 15px; border-radius: 10px; margin-bottom: 15px; text-align: center; color: white; }
    .diamond { background-color: #6f42c1; border: 2px solid #fff; }
    .gold { background-color: #fd7e14; border: 2px solid #fff; }
    .silver { background-color: #004085; border: 2px solid #fff; }
    .blitz { background-color: #28a745; border: 2px solid #fff; }
    .hold { background-color: #495057; border: 1px dashed #ccc; }
    /* 탭 스타일 조정 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #4e8cff; color: white; }
</style>
""", unsafe_allow_html=True)

check_years = 3

# -----------------------------------------------------------------------------
# 2. 데이터 가져오기 및 처리 (연결 안정성 강화 버전)
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
            
            # --- 기술적 지표 계산 ---
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
            
        except Exception:
            time.sleep(1)
            continue

    return None

# -----------------------------------------------------------------------------
# 3. 지갑 및 포트폴리오 관리 시스템
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
    if strategy_type == "Blitz" or strategy_type == "블리츠":
        key = "blitz_cash"
    else:
        key = "hunter_cash"
    
    if action == "deposit":
        data[key] += amount
    elif action == "buy":
        data[key] -= amount
    elif action == "sell":
        data[key] += amount
        
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
        total_sell_amt = sold_info["sell_price"] * sold_info["qty"]
        tier_name = sold_info["tier"]
        wallet_type = "Blitz" if "블리츠" in tier_name else "Hunter"
        
        update_cash(wallet_type, total_sell_amt, "sell")
        save_json(PORTFOLIO_FILE, data)
        return True, total_sell_amt, wallet_type
        
    return False, 0, ""

# -----------------------------------------------------------------------------
# 5. 메인 앱 구조
# -----------------------------------------------------------------------------
try:
    st.sidebar.title("🦅 Hunter V6 System")
    
    # [메뉴 분리] 과거 매매 기록 탭을 추가했습니다.
    menu = st.sidebar.radio(
        "📌 메뉴 선택", 
        ["🚀 SOXL 대시보드 (Main)", "📜 과거 매매 기록 (History)", "📊 SOXL 백테스트 분석"]
    )
    
    # -------------------------------------------------------------------------
    # 공통 데이터 로드 (SOXL 관련 탭일 때만)
    # -------------------------------------------------------------------------
    df = get_data("SOXL")
    if df is None or len(df) < 2:
        st.error("📉 SOXL 데이터 연결 실패. 잠시 후 갱신해주세요.")
        st.stop()

    today = df.iloc[-1]
    prev = df.iloc[-2]
    current_price = today['Close']

    # 지갑 표시 (공통)
    st.sidebar.markdown("---")
    st.sidebar.header("💰 자산 관리 (Wallet)")
    wallet = load_wallet()
    cash_hunter = wallet["hunter_cash"]
    cash_blitz = wallet["blitz_cash"]
    st.sidebar.metric("🦅 Hunter 예수금", f"${cash_hunter:,.0f}")
    st.sidebar.metric("⚡ Blitz 예수금", f"${cash_blitz:,.0f}")
    
    with st.sidebar.expander("💵 예수금 입금/수정"):
        deposit_type = st.radio("계좌 선택", ["Hunter", "Blitz"])
        deposit_amount = st.number_input("금액 ($)", step=100)
        if st.button("입금/수정 반영"):
            update_cash(deposit_type, deposit_amount, "deposit")
            st.rerun()
            
    if st.sidebar.button("데이터/잔고 갱신"):
        st.cache_data.clear()
        st.rerun()

    # ---------------------------------------------------------------------
    # [PAGE 1] 대시보드 (현재 보유 자산까지만 표시)
    # ---------------------------------------------------------------------
    if menu == "🚀 SOXL 대시보드 (Main)":
        st.title("🦅 SOXL Hunter Dashboard")
        st.markdown("---")
        
        # 상단 정보창
        change_val = current_price - prev['Close']
        change_pct = (change_val / prev['Close']) * 100
        color_css = "color: #ff4b4b;" if change_pct >= 0 else "color: #4b88ff;"
        sign = "+" if change_pct >= 0 else ""
        candle_text = "🔴 양봉" if today['Close'] >= today['Open'] else "🔵 음봉"
        vol_str = "🔥 폭발" if today['Vol_Ratio'] >= 1.5 else "평범"

        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f"""<div style="text-align: left; line-height: 1.2;"><span style="font-size: 14px; color: gray;">SOXL 현재가</span><br><span style="font-size: 32px; font-weight: bold;">${current_price:.2f}</span><br><span style="font-size: 12px; color: gray;">(전일대비) </span><span style="font-size: 15px; font-weight: bold; {color_css}">{sign}{change_pct:.2f}%</span></div>""", unsafe_allow_html=True)
        with c2: st.markdown(f"""<div style="text-align: left; line-height: 1.2;"><span style="font-size: 14px; color: gray;">Sigma (20일)</span><br><span style="font-size: 32px; font-weight: bold;">{today['Sigma']:.2f}</span><br><span style="font-size: 14px; color: gray;">표준편차 등락</span></div>""", unsafe_allow_html=True)
        with c3: st.markdown(f"""<div style="text-align: left; line-height: 1.2;"><span style="font-size: 14px; color: gray;">RSI (14일)</span><br><span style="font-size: 32px; font-weight: bold;">{today['RSI']:.1f}</span><br><span style="font-size: 14px; color: gray;">상대강도지수</span></div>""", unsafe_allow_html=True)
        with c4: st.markdown(f"""<div style="text-align: left; line-height: 1.2;"><span style="font-size: 14px; color: gray;">거래량 강도</span><br><span style="font-size: 32px; font-weight: bold;">{today['Vol_Ratio']:.2f}배</span><br><span style="font-size: 14px; color: #555;">{vol_str} / {candle_text}</span></div>""", unsafe_allow_html=True)

        # 신호 로직
        st.markdown("---")
        st.subheader("📢 오늘 매수 신호 분석 (Tier Status)")
        sig, sig60 = today['Sigma'], today['Sigma60']
        rsi, vol_r = today['RSI'], today['Vol_Ratio']
        is_dia = (sig <= -2.5) and (rsi < 30) and (vol_r >= 1.5)
        is_gold = ((sig <= -2.0) and (rsi < 30) and (vol_r >= 1.5)) or ((sig <= -1.8) and (sig60 <= -2.0))
        is_gold = is_gold and (not is_dia)
        cond_silver = (rsi < 45) and (today['Pct_B'] < 0.2) and (today['Close'] > today['MA120']) and (not is_dia) and (not is_gold)
        is_silver = cond_silver and today['Is_Yangbong']
        is_blitz = (today['RSI2'] < 5) and (today['Close'] > today['MA200'])

        col_d, col_g, col_s = st.columns(3)
        with col_d:
            if is_dia: st.markdown(f"""<div class="signal-box diamond"><div class="big-font">💎 DIAMOND: ON</div><p>인생 역전 기회</p><hr><strong>80% 매수</strong><br><span style="font-size:0.8em">5일 강제 보유</span></div>""", unsafe_allow_html=True)
            else: st.markdown(f"""<div class="signal-box hold"><div class="big-font">💎 DIAMOND: OFF</div><p>조건 미충족</p><hr><strong>-</strong><br><span style="font-size:0.8em">현재 Sigma: {sig:.2f}</span></div>""", unsafe_allow_html=True)
            if cond_silver and today['Is_Yangbong']: st.markdown("""<div class="signal-box pyramid"><strong>🔥 불타기 찬스</strong></div>""", unsafe_allow_html=True)
        with col_g:
            if is_gold: st.markdown(f"""<div class="signal-box gold"><div class="big-font">🥇 GOLD: ON</div><p>강력 과매도</p><hr><strong>50% 매수</strong></div>""", unsafe_allow_html=True)
            else: st.markdown(f"""<div class="signal-box hold"><div class="big-font">🥇 GOLD: OFF</div><p>조건 미충족</p><hr><strong>-</strong></div>""", unsafe_allow_html=True)
        with col_s:
            if is_silver: st.markdown(f"""<div class="signal-box silver"><div class="big-font">🥈 SILVER: ON</div><p>눌림목 진입</p><hr><strong>20% 매수</strong></div>""", unsafe_allow_html=True)
            else: st.markdown(f"""<div class="signal-box hold"><div class="big-font">🥈 SILVER: OFF</div><p>조건 미충족</p><hr><strong>-</strong></div>""", unsafe_allow_html=True)
        
        if is_blitz: st.success("⚡ **Blitz 신호 발생!** (RSI2 < 5 & 상승장) → 단타 진입 추천")

        st.markdown("---")
        st.subheader("🛡️ 청산 가이드 (Manual)")
        c_sell_1, c_sell_2 = st.columns(2)
        with c_sell_1: st.info("**🦅 [Hunter]**\n- 💎 다이아: -40% TS\n- 🥇 골드: -20% TS\n- 🥈 실버: -15% TS")
        with c_sell_2: st.success("**⚡ [Blitz]**\n- 🎯 익절: +10%\n- 🛑 손절: -15%")

        # ----------------------------------------------
        # 현재 보유 자산 (Holding Only)
        # ----------------------------------------------
        st.markdown("---")
        st.subheader("💼 현재 보유 자산 (My Portfolio)")
        
        with st.expander("➕ 매수 기록 추가", expanded=False):
            c_in1, c_in2, c_in3, c_in4, c_in5 = st.columns(5)
            input_date = c_in1.date_input("매수 날짜", datetime.now())
            input_tier = c_in2.selectbox("등급", ["💎 다이아", "🥇 골드", "🥈 실버", "⚡ 블리츠", "기타"])
            input_price = c_in3.number_input("단가($)", min_value=0.0, step=0.01, format="%.2f")
            input_qty = c_in4.number_input("수량", min_value=1, step=1)
            if c_in5.button("매수 저장"):
                if input_price > 0:
                    total = input_price * input_qty
                    w_key = "blitz_cash" if "블리츠" in input_tier else "hunter_cash"
                    w_type = "Blitz" if "블리츠" in input_tier else "Hunter"
                    if load_wallet()[w_key] >= total:
                        update_cash(w_type, total, "buy")
                        add_trade(input_date, input_tier, input_price, input_qty)
                        st.success("매수 완료!")
                        time.sleep(1)
                        st.rerun()
                    else: st.error("잔고 부족")

        portfolio_data = load_portfolio()
        holdings = [t for t in portfolio_data if t['status'] == 'holding']
        
        if holdings:
            df_hold = pd.DataFrame(holdings)
            df_hold['current_price'] = current_price
            df_hold['profit_pct'] = ((df_hold['current_price'] - df_hold['price']) / df_hold['price']) * 100
            df_hold['profit_val'] = (df_hold['current_price'] - df_hold['price']) * df_hold['qty']
            df_hold = df_hold.sort_values("date", ascending=False)
            
            total_val = (df_hold['current_price'] * df_hold['qty']).sum()
            st.markdown(f"**총 평가액: ${total_val:,.2f}**")

            for index, row in df_hold.iterrows():
                pct = row['profit_pct']
                color = "red" if pct > 0 else "blue"
                sign = "+" if pct > 0 else ""
                
                # TS 계산
                ts_note = ""
                try:
                    peak = df.loc[df.index.strftime('%Y-%m-%d') >= row['date']]['Close'].max()
                    peak = max(peak, current_price) if not np.isnan(peak) else current_price
                    if "다이아" in row['tier']: ts_price = peak * 0.6
                    elif "골드" in row['tier']: ts_price = peak * 0.8
                    elif "실버" in row['tier']: ts_price = peak * 0.85
                    else: ts_price = row['price'] * 0.85
                    ts_note = f"TS: ${ts_price:.2f}"
                except: ts_note = "-"

                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 1.5, 2.5, 3], vertical_alignment="center")
                    c1.markdown(f"**{row['date']}**\n\n{row['tier']}")
                    c2.markdown(f"평단: **${row['price']:.2f}**\n\n수량: {row['qty']}주")
                    c3.markdown(f"현재: **${current_price:.2f}**\n\n{ts_note}")
                    c4.markdown(f"수익률: :{color}[**{sign}{pct:.2f}%**]\n\n수익금: :{color}[**{sign}${row['profit_val']:.2f}**]")
                    
                    with c5:
                        cc1, cc2 = st.columns([1.5, 1], vertical_alignment="center")
                        manual_sell = cc1.number_input("매도가", value=float(current_price), step=0.01, key=f"s_{row['id']}", label_visibility="collapsed")
                        if cc2.button("매도", key=f"btn_{row['id']}"):
                            success, amt, w = sell_trade(row['id'], manual_sell)
                            if success:
                                st.success(f"매도 완료! {w}에 +${amt:,.2f}")
                                time.sleep(1)
                                st.rerun()
        else:
            st.info("보유 중인 자산이 없습니다.")

    # ---------------------------------------------------------------------
    # [PAGE 2] 과거 매매 기록 (NEW TAB) - 완벽한 분리 & 자동 정렬
    # ---------------------------------------------------------------------
    elif menu == "📜 과거 매매 기록 (History)":
        st.title("📜 나의 사냥 일지 (Trade History)")
        st.markdown("---")
        
        portfolio_data = load_portfolio()
        history = [t for t in portfolio_data if t['status'] == 'sold']
        
        if history:
            st.metric("총 매매 횟수", f"{len(history)}회")
            
            df_hist = pd.DataFrame(history)
            df_hist['profit_pct'] = ((df_hist['sell_price'] - df_hist['price']) / df_hist['price']) * 100
            df_hist['profit_val'] = (df_hist['sell_price'] - df_hist['price']) * df_hist['qty']
            df_hist = df_hist.sort_values("sell_date", ascending=False)
            
            for index, row in df_hist.iterrows():
                pct = row['profit_pct']
                color = "#ff4b4b" if pct > 0 else "#4b88ff"
                sign = "+" if pct > 0 else ""
                
                try:
                    d1 = datetime.strptime(row['date'], "%Y-%m-%d")
                    d2 = datetime.strptime(row['sell_date'], "%Y-%m-%d")
                    days = (d2 - d1).days
                    period = f"{days}일 보유"
                except: period = "-"

                # [디자인] 넓은 화면을 활용한 깔끔한 레이아웃 + 세로 중앙 정렬
                with st.container(border=True):
                    # 전체 컬럼: 티어 | 날짜 | 가격 | 수량 | 수익 | 삭제버튼
                    c1, c2, c3, c4, c5, c6 = st.columns([1.2, 2.0, 2.0, 1.0, 2.0, 0.5], vertical_alignment="center")
                    
                    # 1. 티어
                    with c1:
                        st.markdown(f"<div style='text-align: center; font-size: 1.5rem; font-weight: bold;'>{row['tier']}</div>", unsafe_allow_html=True)
                    
                    # 2. 날짜
                    with c2:
                        st.markdown(f"""
                        <div style='text-align: center; line-height: 1.4; font-size: 0.9rem; color: #555;'>
                            BUY: <b>{row['date']}</b><br>
                            SELL: <b>{row['sell_date']}</b><br>
                            <span style='background:#f0f2f6; padding:2px 6px; border-radius:4px; font-size:0.8rem;'>{period}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # 3. 가격
                    with c3:
                        st.markdown(f"""
                        <div style='text-align: right; line-height: 1.4; font-size: 0.95rem; color: #555;'>
                            매수: <b>${row['price']:.2f}</b><br>
                            매도: <b>${row['sell_price']:.2f}</b>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    # 4. 수량
                    with c4:
                        st.markdown(f"<div style='text-align: center; font-weight: bold; font-size: 1.1rem;'>{row['qty']}주</div>", unsafe_allow_html=True)
                        
                    # 5. 수익
                    with c5:
                        st.markdown(f"""
                        <div style='text-align: right; color: {color}; line-height: 1.2;'>
                            <div style='font-size: 1.4rem; font-weight: 900;'>{sign}{pct:.2f}%</div>
                            <div style='font-size: 1rem; font-weight: bold;'>{sign}${row['profit_val']:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # 6. 삭제
                    with c6:
                        if st.button("🗑️", key=f"del_h_{row['id']}"):
                            delete_trade(row['id'])
                            st.rerun()
        else:
            st.info("아직 매도 완료된 기록이 없습니다.")

    # --- [PAGE 3] 백테스트 ---
    elif menu == "📊 SOXL 백테스트 분석":
        st.title("📊 SOXL 과거 수익률 정밀 검증")
        
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




















