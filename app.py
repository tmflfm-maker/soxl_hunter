import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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
    
    /* 매도 섹션 스타일 */
    .sell-section { background-color: rgba(255, 75, 75, 0.1); padding: 10px; border-radius: 5px; border: 1px solid rgba(255, 75, 75, 0.3); }
    .ts-price { font-weight: bold; color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

check_years = 3

# -----------------------------------------------------------------------------
# 2. 데이터 가져오기 및 처리
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_data():
    for attempt in range(3):
        try:
            df = yf.download("SOXL", period=f"{check_years}y", interval="1d", progress=False)
            
            if df.empty or len(df) < 20:
                time.sleep(1)
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # 기술적 지표 계산
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA120'] = df['Close'].rolling(window=120).mean()
            df['MA200'] = df['Close'].rolling(window=200).mean()
            
            # 볼린저 밴드
            df['BB_Mid'] = df['MA20']
            df['BB_Std'] = df['Close'].rolling(window=20).std()
            df['BB_Lower'] = df['BB_Mid'] - (2 * df['BB_Std'])
            denom = (df['BB_Mid'] + (2 * df['BB_Std'])) - df['BB_Lower']
            df['Pct_B'] = np.where(denom == 0, 0, (df['Close'] - df['BB_Lower']) / denom)

            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # RSI2 (Blitz)
            gain2 = (delta.where(delta > 0, 0)).rolling(window=2).mean()
            loss2 = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
            rs2 = gain2 / loss2
            df['RSI2'] = 100 - (100 / (1 + rs2))
            
            # Sigma
            df['Return'] = df['Close'].pct_change()
            mean_20 = df['Return'].rolling(window=20).mean()
            std_20 = df['Return'].rolling(window=20).std()
            df['Sigma'] = (df['Return'] - mean_20) / std_20
            
            mean_60 = df['Return'].rolling(window=60).mean()
            std_60 = df['Return'].rolling(window=60).std()
            df['Sigma60'] = (df['Return'] - mean_60) / std_60
            
            # Volume
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
    # 전략 타입 매핑
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

# [수정됨] 매도 처리 함수 (입력받은 매도 단가 사용)
def sell_trade(trade_id, sell_price):
    data = load_portfolio()
    sold_info = None
    
    for t in data:
        if t["id"] == trade_id and t["status"] == "holding":
            t["status"] = "sold"
            t["sell_price"] = float(sell_price) # 입력받은 가격 저장
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
# 4. 메인 앱 구조
# -----------------------------------------------------------------------------
try:
    df = get_data()

    if df is None or len(df) < 2:
        st.error("📉 야후 파이낸스 연결이 원활하지 않습니다. 잠시 후 왼쪽 사이드바의 '데이터/잔고 갱신' 버튼을 눌러주세요.")
        st.stop()

    today = df.iloc[-1]
    prev = df.iloc[-2]
    current_price = today['Close']

    # --- [사이드바] 네비게이션 및 자산 관리 ---
    st.sidebar.title("🦅 SOXL Hunter V6")
    menu = st.sidebar.radio("📌 메뉴 선택", ["🚀 대시보드 (Signal)", "📊 백테스트 상세 분석"])
    
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

    # =========================================================================
    # [PAGE 1] 대시보드 (Signal)
    # =========================================================================
    if menu == "🚀 대시보드 (Signal)":
        st.title("🦅 오늘의 매수 신호 (Dashboard)")
        st.markdown("---")

        # 1. 상단 정보창
        change_val = current_price - prev['Close']
        change_pct = (change_val / prev['Close']) * 100
        
        if change_pct >= 0:
            color_css = "color: #ff4b4b;"
            sign = "+"
        else:
            color_css = "color: #4b88ff;"
            sign = ""
        
        candle_text = "🔴 양봉" if today['Close'] >= today['Open'] else "🔵 음봉"
        vol_str = "🔥 폭발" if today['Vol_Ratio'] >= 1.5 else "평범"

        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">SOXL 현재가</span><br>
                <span style="font-size: 32px; font-weight: bold;">${current_price:.2f}</span><br>
                <span style="font-size: 12px; color: gray;">(전일대비) </span>
                <span style="font-size: 15px; font-weight: bold; {color_css}">{sign}{change_pct:.2f}%</span>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">Sigma (20일)</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['Sigma']:.2f}</span><br>
                <span style="font-size: 14px; color: gray;">표준편차 등락</span>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">RSI (14일)</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['RSI']:.1f}</span><br>
                <span style="font-size: 14px; color: gray;">상대강도지수</span>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">거래량 강도</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['Vol_Ratio']:.2f}배</span><br>
                <span style="font-size: 14px; color: #555;">{vol_str} / {candle_text}</span>
            </div>
            """, unsafe_allow_html=True)

        # 2. 신호 로직
        st.markdown("---")
        st.subheader("📢 오늘 매수 신호 분석 (Tier Status)")
        
        sig, sig60 = today['Sigma'], today['Sigma60']
        rsi, vol_r = today['RSI'], today['Vol_Ratio']
        pct_b, close = today['Pct_B'], today['Close']
        ma120, ma200 = today['MA120'], today['MA200']
        is_yang = today['Is_Yangbong']

        is_dia = (sig <= -2.5) and (rsi < 30) and (vol_r >= 1.5)
        is_gold_std = (sig <= -2.0) and (rsi < 30) and (vol_r >= 1.5)
        is_gold_dual = (sig <= -1.8) and (sig60 <= -2.0)
        is_gold = (is_gold_std or is_gold_dual) and (not is_dia)
        cond_silver_base = (rsi < 45) and (pct_b < 0.2) and (close > ma120) and (not is_dia) and (not is_gold)
        is_silver = cond_silver_base and is_yang
        is_blitz = (today['RSI2'] < 5) and (close > ma200)

        col_d, col_g, col_s = st.columns(3)

        with col_d:
            if is_dia:
                d_cls, d_title, d_msg = "diamond", "💎 DIAMOND: ON", "인생 역전 기회 (Sniper)"
                d_act = f"메인 80% 매수<br>(${cash_hunter*0.8:,.0f})"
                d_note = "5일 강제 보유 필수"
            else:
                d_cls, d_title, d_msg = "hold", "💎 DIAMOND: OFF", "조건 미충족"
                d_act = "-"
                d_note = f"현재 Sigma: {sig:.2f} (목표 -2.5)"

            st.markdown(f"""<div class="signal-box {d_cls}"><div class="big-font">{d_title}</div><p>{d_msg}</p><hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);"><strong>{d_act}</strong><br><span style="font-size: 0.8em; opacity: 0.8;">{d_note}</span></div>""", unsafe_allow_html=True)
            if cond_silver_base and is_yang:
                 st.markdown("""<div class="signal-box pyramid"><strong>🔥 불타기 찬스</strong><br><span style="font-size:0.8em">다이아 보유중이면 추가매수</span></div>""", unsafe_allow_html=True)

        with col_g:
            if is_gold:
                g_cls, g_title, g_msg = "gold", "🥇 GOLD: ON", "강력 과매도 (Trend)"
                g_act = f"메인 50% 매수<br>(${cash_hunter*0.5:,.0f})"
                g_note = "정석 조건 만족" if is_gold_std else f"Dual Sigma 발동 (S60:{sig60:.2f})"
            else:
                g_cls, g_title, g_msg = "hold", "🥇 GOLD: OFF", "조건 미충족"
                g_act = "-"
                g_note = f"현재 Sigma: {sig:.2f} (목표 -2.0)"
            st.markdown(f"""<div class="signal-box {g_cls}"><div class="big-font">{g_title}</div><p>{g_msg}</p><hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);"><strong>{g_act}</strong><br><span style="font-size: 0.8em; opacity: 0.8;">{g_note}</span></div>""", unsafe_allow_html=True)

        with col_s:
            if is_silver:
                s_cls, s_title, s_msg = "silver", "🥈 SILVER: ON", "상승장 눌림목 (Scavenger)"
                s_act = f"메인 20% 매수<br>(${cash_hunter*0.2:,.0f})"
                s_note = "양봉 확인됨. 진입 가능."
            elif cond_silver_base and not is_yang:
                s_cls, s_title, s_msg = "hold", "🥈 SILVER: WAIT", "자리는 좋으나 '음봉'임"
                s_act = "매수 금지 (대기)"
                s_note = "내일 양봉 뜨면 진입하세요."
            else:
                s_cls, s_title, s_msg = "hold", "🥈 SILVER: OFF", "조건 미충족"
                s_act = "-"
                s_note = f"RSI: {rsi:.1f} / %B: {pct_b:.2f}"
            st.markdown(f"""<div class="signal-box {s_cls}"><div class="big-font">{s_title}</div><p>{s_msg}</p><hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);"><strong>{s_act}</strong><br><span style="font-size: 0.8em; opacity: 0.8;">{s_note}</span></div>""", unsafe_allow_html=True)
        
        if is_blitz:
            st.success(f"⚡ **Blitz 신호 발생!** (RSI2 < 5 & 상승장) → 단타 진입 추천 (${cash_blitz:,.0f} 사용 가능)")

        st.info("💡 팁: 과거 성과와 15일 수익률 분석을 보려면 사이드바 메뉴에서 **'📊 백테스트 상세 분석'**을 선택하세요.")

        # 3. 청산 가이드
        st.markdown("---")
        st.subheader("🛡️ 청산 가이드 (Manual)")
        c_sell_1, c_sell_2 = st.columns(2)
        with c_sell_1:
            st.info("""**🦅 [Hunter 전략 매도]**\n- 💎 **다이아:** 5일간 절대 매도 금지 → 이후 고점 대비 -40% TS\n- 🥇 **골드:** 고점 대비 -20% TS\n- 🥈 **실버:** 고점 대비 -15% TS""")
        with c_sell_2:
            st.success(f"""**⚡ [Blitz 전략 매도]**\n- 🎯 **익절:** 진입가 +10% (${current_price*1.1:.2f})\n- 🛑 **손절:** 진입가 -15% (${current_price*0.85:.2f})""")
        st.caption("※ 거래량 강도: 당일 거래량 / 20일 평균. 1.5배 이상이면 '투매'로 간주하여 신뢰도 상승.")

        # =====================================================================
        # 4. 현재 보유 자산 및 매매 기록 (My Portfolio)
        # =====================================================================
        st.markdown("---")
        st.subheader("💼 포트폴리오 관리 (My Portfolio)")

        # 4-1. 입력 폼
        with st.expander("➕ 매매 기록 수기 입력 (Trade Log)", expanded=False):
            c_in1, c_in2, c_in3, c_in4, c_in5 = st.columns(5)
            with c_in1:
                input_date = st.date_input("매수 날짜", datetime.now())
            with c_in2:
                input_tier = st.selectbox("진입 등급 (Tier)", ["💎 다이아", "🥇 골드", "🥈 실버", "⚡ 블리츠", "기타"])
            with c_in3:
                input_price = st.number_input("매수 단가 ($)", min_value=0.0, step=0.01, format="%.2f")
            with c_in4:
                input_qty = st.number_input("매수 수량 (주)", min_value=1, step=1)
            with c_in5:
                st.write("") 
                st.write("") 
                
                if st.button("기록 저장"):
                    if input_price > 0 and input_qty > 0:
                        total_cost = input_price * input_qty
                        
                        if "블리츠" in input_tier:
                            stype = "Blitz"
                            wallet_key = "blitz_cash"
                        else:
                            stype = "Hunter"
                            wallet_key = "hunter_cash"
                        
                        current_wallet = load_wallet()
                        if current_wallet[wallet_key] >= total_cost:
                            update_cash(stype, total_cost, "buy")
                            add_trade(input_date, input_tier, input_price, input_qty)
                            st.success(f"매수 완료! {stype} 예수금에서 ${total_cost:,.2f} 차감되었습니다.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"잔고가 부족합니다! (필요: ${total_cost:,.2f}, 보유: ${current_wallet[wallet_key]:,.2f})")
                    else:
                        st.error("가격과 수량을 확인하세요.")

        # 4-2. 포트폴리오 데이터 처리
        portfolio_data = load_portfolio()
        
        holdings = [t for t in portfolio_data if t['status'] == 'holding']
        history = [t for t in portfolio_data if t['status'] == 'sold']

        # ---------------------------------------------------------------------
        # [섹션 1] 현재 보유 자산 (Holding)
        # ---------------------------------------------------------------------
        st.markdown(f"#### 🔥 현재 보유 자산 ({len(holdings)}건)")
        
        if holdings:
            df_hold = pd.DataFrame(holdings)
            df_hold['current_price'] = current_price
            df_hold['profit_pct'] = ((df_hold['current_price'] - df_hold['price']) / df_hold['price']) * 100
            df_hold['profit_val'] = (df_hold['current_price'] - df_hold['price']) * df_hold['qty']
            df_hold = df_hold.sort_values("date", ascending=False)
            
            total_val = (df_hold['current_price'] * df_hold['qty']).sum()
            total_profit = df_hold['profit_val'].sum()
            total_profit_color = "red" if total_profit > 0 else "blue"
            
            st.markdown(f"**총 평가액:** :blue[${total_val:,.2f}] / **총 수익금:** :{total_profit_color}[${total_profit:,.2f}]")

            for index, row in df_hold.iterrows():
                pct = row['profit_pct']
                color = "red" if pct > 0 else "blue"
                sign = "+" if pct > 0 else ""
                
                # --- [핵심] 실시간 청산가(Trailing Stop) 계산 로직 ---
                ts_note = ""
                ts_price = 0.0
                
                try:
                    buy_date_str = row['date']
                    # 매수일 이후의 데이터 조회
                    period_mask = df.index.strftime('%Y-%m-%d') >= buy_date_str
                    period_df = df.loc[period_mask]
                    
                    if not period_df.empty:
                        # 매수일 이후 최고 종가 (Peak)
                        peak_price = period_df['Close'].max()
                        # 오늘 현재가가 더 높다면 Peak 갱신
                        peak_price = max(peak_price, current_price)
                    else:
                        peak_price = current_price # 데이터 없으면 현재가
                    
                    # 티어별 로직 적용
                    if "다이아" in row['tier']:
                        # 5일 의무 보유 체크
                        buy_dt = datetime.strptime(buy_date_str, "%Y-%m-%d")
                        days_held = (datetime.now() - buy_dt).days
                        if days_held < 5:
                            ts_note = f"🔒 5일 의무보유 ({days_held}일차)"
                        else:
                            ts_price = peak_price * 0.60 # -40%
                            ts_note = f"TS: ${ts_price:.2f} (고점대비 -40%)"
                    
                    elif "골드" in row['tier']:
                        ts_price = peak_price * 0.80 # -20%
                        ts_note = f"TS: ${ts_price:.2f} (고점대비 -20%)"
                        
                    elif "실버" in row['tier']:
                        ts_price = peak_price * 0.85 # -15%
                        ts_note = f"TS: ${ts_price:.2f} (고점대비 -15%)"
                        
                    elif "블리츠" in row['tier']:
                        # 블리츠는 매수가 기준 손절 -15%
                        ts_price = row['price'] * 0.85
                        ts_note = f"Stop: ${ts_price:.2f} (매수가대비 -15%)"
                    
                    else:
                        ts_note = "-"

                except Exception as e:
                    ts_note = "계산 불가"

                # ----------------------------------------------------
                
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 1.5, 2.5, 3])
                    
                    with c1:
                        st.markdown(f"**{row['date']}**")
                        st.caption(f"{row['tier']}")
                    with c2:
                        st.markdown(f"평단: **${row['price']:.2f}**")
                        st.caption(f"수량: {row['qty']}주")
                    with c3:
                        st.markdown(f"현재: **${current_price:.2f}**")
                        st.caption(f"최고점: ${peak_price:.2f}" if 'peak_price' in locals() else "")
                    with c4:
                        st.markdown(f"수익률: :{color}[**{sign}{pct:.2f}%**]")
                        st.markdown(f"수익금: :{color}[**{sign}${row['profit_val']:.2f}**]")
                    with c5:
                        # 매도 섹션 (입력창 + 버튼)
                        with st.container():
                            # 청산 가이드 표시
                            if ts_note:
                                st.markdown(f"<span class='ts-price'>⚠️ {ts_note}</span>", unsafe_allow_html=True)
                            
                            c_sell_in, c_sell_btn, c_del = st.columns([1.5, 1, 0.5])
                            with c_sell_in:
                                # 매도 단가 입력 (기본값: 현재가)
                                manual_sell_price = st.number_input("매도단가", value=float(current_price), step=0.01, format="%.2f", label_visibility="collapsed", key=f"sell_input_{row['id']}")
                            with c_sell_btn:
                                if st.button("매도", key=f"sell_{row['id']}"):
                                    success, amt, w_type = sell_trade(row['id'], manual_sell_price)
                                    if success:
                                        st.success(f"매도 완료! (+${amt:,.2f})")
                                        time.sleep(1)
                                        st.rerun()
                            with c_del:
                                if st.button("🗑️", key=f"del_{row['id']}"):
                                    delete_trade(row['id'])
                                    st.rerun()
                    st.markdown("---")
        else:
            st.info("현재 보유 중인 자산이 없습니다.")

      # ---------------------------------------------------------------------
        # [섹션 2] 과거 매매 기록 (History) - 높이 고정 & 강제 중앙 정렬 (Flexbox)
        # ---------------------------------------------------------------------
        st.markdown(f"#### 📜 과거 매매 기록 ({len(history)}건)")
        
        if history:
            df_hist = pd.DataFrame(history)
            # 매도 당시 가격 기준 수익률 계산
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
                    hold_days = (d2 - d1).days
                    period_text = f"({hold_days}일 보유)"
                except:
                    period_text = "(-)"

                with st.container(border=True):
                    # [핵심 1] vertical_alignment="center" : 스트림릿 차원에서의 중앙 정렬
                    c_tier, c_date, c_price, c_qty, c_profit, c_del = st.columns([1.2, 2.5, 1.8, 0.8, 2.2, 0.5], vertical_alignment="center")
                    
                    # [핵심 2] 모든 칸의 높이를 이 변수로 통일합니다. (필요하면 90px, 100px로 늘려보세요)
                    ROW_HEIGHT = "100px"
                    
                    # 1. 티어 (정중앙)
                    with c_tier:
                        st.markdown(f"""
                        <div style="height: {ROW_HEIGHT}; display: flex; align-items: center; justify-content: center;">
                            <span style="font-size: 1.5rem; font-weight: 900;">{row['tier']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    # 2. 날짜 (세로 방향 중앙 정렬)
                    with c_date:
                         st.markdown(f"""
                        <div style="height: {ROW_HEIGHT}; display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1.4;">
                            <div><span style="color: gray; font-size: 0.9em;">Buy:</span> <strong>{row['date']}</strong></div>
                            <div><span style="color: gray; font-size: 0.9em;">Sell:</span> <strong>{row['sell_date']}</strong></div>
                            <div style="margin-top: 4px;"><span style="font-size: 0.85em; color: #555; background-color: #f0f2f6; padding: 2px 6px; border-radius: 4px;">{period_text}</span></div>
                        </div>
                        """, unsafe_allow_html=True)

                    # 3. 매수/매도 단가 (우측 중앙 정렬)
                    with c_price:
                        st.markdown(f"""
                        <div style="height: {ROW_HEIGHT}; display: flex; flex-direction: column; align-items: flex-end; justify-content: center; line-height: 1.5; padding-right: 10px;">
                            <div><span style="color: gray; font-size: 0.9em;">매수:</span> <strong>${row['price']:.2f}</strong></div>
                            <div><span style="color: gray; font-size: 0.9em;">매도:</span> <strong>${row['sell_price']:.2f}</strong></div>
                        </div>
                        """, unsafe_allow_html=True)

                    # 4. 수량 (정중앙)
                    with c_qty:
                        st.markdown(f"""
                        <div style="height: {ROW_HEIGHT}; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                            <span style="color: gray; font-size: 0.9em;">수량</span>
                            <span style="font-size: 1.1rem; font-weight: bold;">{row['qty']}<span style="font-size: 0.8rem;">주</span></span>
                        </div>
                        """, unsafe_allow_html=True)

                    # 5. 수익률 (우측 중앙)
                    with c_profit:
                        st.markdown(f"""
                        <div style="height: {ROW_HEIGHT}; display: flex; flex-direction: column; align-items: flex-end; justify-content: center; color: {color}; line-height: 1.2;">
                            <div style="font-size: 1.5rem; font-weight: 900;">{sign}{pct:.2f}%</div>
                            <div style="font-size: 1.0rem; font-weight: bold; opacity: 0.9;">{sign}${row['profit_val']:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    # 6. 삭제 버튼 (자동 중앙)
                    with c_del:
                        if st.button("🗑️", key=f"del_hist_{row['id']}"):
                            delete_trade(row['id'])
                            st.rerun()
        else:
            st.info("아직 완료된 매매 기록이 없습니다.")
    # =========================================================================
    # [PAGE 2] 백테스트 상세 분석
    # =========================================================================
    elif menu == "📊 백테스트 상세 분석":
        st.title("📊 과거 신호 수익률 정밀 검증")
        st.markdown(f"최근 {check_years}년 데이터 기준 시뮬레이션입니다.")
        
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
            price_5d = np.nan
            price_15d = np.nan
            
            if i + 5 < len(df):
                price_5d = df['Close'].iloc[i+5]
                ret_5d = ((price_5d - price_buy) / price_buy) * 100
            
            if i + 15 < len(df):
                price_15d = df['Close'].iloc[i+15]
                ret_15d = ((price_15d - price_buy) / price_buy) * 100

            history.append({
                "날짜": date_str,
                "등급": tier,
                "매수가": price_buy,
                "5일후_주가": price_5d,
                "수익률(5일)": ret_5d,
                "15일후_주가": price_15d,
                "수익률(15일)": ret_15d
            })

        if history:
            df_hist = pd.DataFrame(history)
            df_hist = df_hist.sort_values("날짜", ascending=False)

            st.subheader("📈 전체 신호 승률 분석")
            
            valid_5d = df_hist.dropna(subset=['수익률(5일)'])
            valid_15d = df_hist.dropna(subset=['수익률(15일)'])
            
            win_5d = (valid_5d['수익률(5일)'] > 0).sum()
            win_15d = (valid_15d['수익률(15일)'] > 0).sum()
            
            rate_5d = (win_5d / len(valid_5d) * 100) if len(valid_5d) > 0 else 0
            rate_15d = (win_15d / len(valid_15d) * 100) if len(valid_15d) > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("총 포착 신호", f"{len(df_hist)}회")
            with m2: st.metric("5일 후 승률 (익절)", f"{rate_5d:.1f}%")
            with m3: st.metric("15일 후 승률 (익절)", f"{rate_15d:.1f}%")
            
            st.markdown("---")

            st.subheader("📋 신호 발생 이력 요약")
            
            df_display = df_hist[['날짜', '등급', '매수가', '수익률(5일)', '수익률(15일)']].copy()
            
            def color_returns(val):
                if pd.isna(val): return ""
                color = '#ff4b4b' if val > 0 else '#4b88ff'
                return f'color: {color}; font-weight: bold;'

            st.dataframe(
                df_display.style
                .format({
                    "매수가": "${:.2f}",
                    "수익률(5일)": "{:+.2f}%",
                    "수익률(15일)": "{:+.2f}%"
                }, na_rep="-")
                .map(color_returns, subset=['수익률(5일)', '수익률(15일)']),
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("---")
            st.subheader("📥 전체 데이터 다운로드")
            st.write("상세 분석을 위해 전체 데이터를 엑셀(CSV)로 받으세요.")
            
            csv = df_hist.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📊 전체 분석 데이터 다운로드 (CSV)",
                data=csv,
                file_name='soxl_hunter_backtest.csv',
                mime='text/csv',
            )
        else:
            st.write("해당 기간 내 신호가 없습니다.")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")


















