import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json
import os

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
# 2. 데이터 가져오기 및 처리
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_data():
    df = yf.download("SOXL", period=f"{check_years}y", interval="1d", progress=False)
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

# -----------------------------------------------------------------------------
# 3. 지갑 관리 시스템
# -----------------------------------------------------------------------------
WALLET_FILE = "my_wallet.json"

def load_wallet():
    if not os.path.exists(WALLET_FILE):
        default_data = {"hunter_cash": 700.0, "blitz_cash": 300.0}
        with open(WALLET_FILE, "w") as f:
            json.dump(default_data, f)
        return default_data
    with open(WALLET_FILE, "r") as f:
        return json.load(f)

def save_wallet(data):
    with open(WALLET_FILE, "w") as f:
        json.dump(data, f)

def update_cash(strategy_type, amount, action):
    data = load_wallet()
    key = "hunter_cash" if strategy_type == "Hunter" else "blitz_cash"
    if action == "deposit":
        data[key] += amount
    elif action == "buy":
        data[key] -= amount
    elif action == "sell":
        data[key] += amount
    save_wallet(data)
    return data

# -----------------------------------------------------------------------------
# 4. 메인 앱 구조 (사이드바 메뉴 적용)
# -----------------------------------------------------------------------------
try:
    df = get_data()
    today = df.iloc[-1]
    prev = df.iloc[-2]
    current_price = today['Close']

    # --- [사이드바] 네비게이션 및 자산 관리 ---
    st.sidebar.title("🦅 SOXL Hunter V6")
    
    # [메뉴 선택 기능 추가] 여기가 핵심입니다.
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
    # [PAGE 1] 대시보드 (오늘의 신호)
    # =========================================================================
    if menu == "🚀 대시보드 (Signal)":
        st.title("🦅 오늘의 매수 신호 (Dashboard)")
        st.markdown("---")

        # 1. 상단 정보창 (HTML 스타일 통일: 모두 굵고 크게)
        change_val = current_price - prev['Close']
        change_pct = (change_val / prev['Close']) * 100
        
        if change_pct >= 0:
            color_css = "color: #ff4b4b;" # 빨강
            sign = "+"
        else:
            color_css = "color: #4b88ff;" # 파랑
            sign = ""
        
        candle_text = "🔴 양봉" if today['Close'] >= today['Open'] else "🔵 음봉"
        vol_str = "🔥 폭발" if today['Vol_Ratio'] >= 1.5 else "평범"

        c1, c2, c3, c4 = st.columns(4)
        
       # c1: 현재가 (전일대비 문구 추가)
        with c1:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">SOXL 현재가</span><br>
                <span style="font-size: 32px; font-weight: bold;">${current_price:.2f}</span><br>
                <span style="font-size: 12px; color: gray;">(전일대비) </span>
                <span style="font-size: 15px; font-weight: bold; {color_css}">{sign}{change_pct:.2f}%</span>
            </div>
            """, unsafe_allow_html=True)
            
        # c2: Sigma (스타일 통일)
        with c2:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">Sigma (20일)</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['Sigma']:.2f}</span><br>
                <span style="font-size: 14px; color: gray;">표준편차 등락</span>
            </div>
            """, unsafe_allow_html=True)

        # c3: RSI (스타일 통일)
        with c3:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">RSI (14일)</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['RSI']:.1f}</span><br>
                <span style="font-size: 14px; color: gray;">상대강도지수</span>
            </div>
            """, unsafe_allow_html=True)

        # c4: 거래량 (스타일 통일)
        with c4:
            st.markdown(f"""
            <div style="text-align: left; line-height: 1.2;">
                <span style="font-size: 14px; color: gray;">거래량 강도</span><br>
                <span style="font-size: 32px; font-weight: bold;">{today['Vol_Ratio']:.2f}배</span><br>
                <span style="font-size: 14px; color: #555;">{vol_str} / {candle_text}</span>
            </div>
            """, unsafe_allow_html=True)

       # ---------------------------------------------------------------------
        # 2. 신호 로직 및 섹션 제목 (상세 수치 표시 기능 복구 완료)
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📢 오늘 매수 신호 분석 (Tier Status)")
        
        # 변수 추출 (편의용)
        sig, sig60 = today['Sigma'], today['Sigma60']
        rsi, vol_r = today['RSI'], today['Vol_Ratio']
        pct_b, close = today['Pct_B'], today['Close']
        ma120, ma200 = today['MA120'], today['MA200']
        is_yang = today['Is_Yangbong']

        # 조건 정의
        is_dia = (sig <= -2.5) and (rsi < 30) and (vol_r >= 1.5)
        
        is_gold_std = (sig <= -2.0) and (rsi < 30) and (vol_r >= 1.5)
        is_gold_dual = (sig <= -1.8) and (sig60 <= -2.0)
        is_gold = (is_gold_std or is_gold_dual) and (not is_dia)
        
        cond_silver_base = (rsi < 45) and (pct_b < 0.2) and (close > ma120) and (not is_dia) and (not is_gold)
        is_silver = cond_silver_base and is_yang
        
        is_blitz = (today['RSI2'] < 5) and (close > ma200)

        # UI 출력 (3단 컬럼)
        col_d, col_g, col_s = st.columns(3)

        # --- 1. Diamond Block ---
        with col_d:
            if is_dia:
                d_cls = "diamond"
                d_title = "💎 DIAMOND: ON"
                d_msg = "인생 역전 기회 (Sniper)"
                d_act = f"메인 80% 매수<br>(${cash_hunter*0.8:,.0f})"
                d_note = "5일 강제 보유 필수"
            else:
                d_cls = "hold"
                d_title = "💎 DIAMOND: OFF"
                d_msg = "조건 미충족"
                d_act = "-"
                # [복구됨] 현재 상태 표시
                d_note = f"현재 Sigma: {sig:.2f} (목표 -2.5)"

            st.markdown(f"""
            <div class="signal-box {d_cls}">
                <div class="big-font">{d_title}</div>
                <p>{d_msg}</p>
                <hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);">
                <strong>{d_act}</strong><br>
                <span style="font-size: 0.8em; opacity: 0.8;">{d_note}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # 불타기 로직
            if cond_silver_base and is_yang:
                 st.markdown("""
                 <div class="signal-box pyramid">
                    <strong>🔥 불타기 찬스</strong><br>
                    <span style="font-size:0.8em">다이아 보유중이면 추가매수</span>
                 </div>
                 """, unsafe_allow_html=True)

        # --- 2. Gold Block ---
        with col_g:
            if is_gold:
                g_cls = "gold"
                g_title = "🥇 GOLD: ON"
                g_msg = "강력 과매도 (Trend)"
                g_act = f"메인 50% 매수<br>(${cash_hunter*0.5:,.0f})"
                if is_gold_std: g_note = "정석 조건 만족"
                else: g_note = f"Dual Sigma 발동 (S60:{sig60:.2f})"
            else:
                g_cls = "hold"
                g_title = "🥇 GOLD: OFF"
                g_msg = "조건 미충족"
                g_act = "-"
                # [복구됨] 현재 상태 표시
                g_note = f"현재 Sigma: {sig:.2f} (목표 -2.0)"

            st.markdown(f"""
            <div class="signal-box {g_cls}">
                <div class="big-font">{g_title}</div>
                <p>{g_msg}</p>
                <hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);">
                <strong>{g_act}</strong><br>
                <span style="font-size: 0.8em; opacity: 0.8;">{g_note}</span>
            </div>
            """, unsafe_allow_html=True)

        # --- 3. Silver Block ---
        with col_s:
            if is_silver:
                s_cls = "silver"
                s_title = "🥈 SILVER: ON"
                s_msg = "상승장 눌림목 (Scavenger)"
                s_act = f"메인 20% 매수<br>(${cash_hunter*0.2:,.0f})"
                s_note = "양봉 확인됨. 진입 가능."
            elif cond_silver_base and not is_yang:
                s_cls = "hold"
                s_title = "🥈 SILVER: WAIT"
                s_msg = "자리는 좋으나 '음봉'임"
                s_act = "매수 금지 (대기)"
                s_note = "내일 양봉 뜨면 진입하세요."
            else:
                s_cls = "hold"
                s_title = "🥈 SILVER: OFF"
                s_msg = "조건 미충족"
                s_act = "-"
                # [복구됨] 현재 상태 표시
                s_note = f"RSI: {rsi:.1f} / %B: {pct_b:.2f}"

            st.markdown(f"""
            <div class="signal-box {s_cls}">
                <div class="big-font">{s_title}</div>
                <p>{s_msg}</p>
                <hr style="margin: 10px 0; border-color: rgba(255,255,255,0.3);">
                <strong>{s_act}</strong><br>
                <span style="font-size: 0.8em; opacity: 0.8;">{s_note}</span>
            </div>
            """, unsafe_allow_html=True)
        
        if is_blitz:
            st.success(f"⚡ **Blitz 신호 발생!** (RSI2 < 5 & 상승장) → 단타 진입 추천 (${cash_blitz:,.0f} 사용 가능)")

        st.info("💡 팁: 과거 성과와 15일 수익률 분석을 보려면 사이드바 메뉴에서 **'📊 백테스트 상세 분석'**을 선택하세요.")
# ---------------------------------------------------------------------
        # 3. 청산 가이드 (누락된 부분 복구)
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.subheader("🛡️ 청산 가이드 (Manual)")
        
        c_sell_1, c_sell_2 = st.columns(2)
        
        with c_sell_1:
            st.info("""
            **🦅 [Hunter 전략 매도]**
            - 💎 **다이아:** 5일간 절대 매도 금지 → 이후 고점 대비 -40% 트레일링 스탑
            - 🥇 **골드:** 고점 대비 -20% 트레일링 스탑
            - 🥈 **실버:** 고점 대비 -15% 트레일링 스탑
            """)
            
        with c_sell_2:
            st.success(f"""
            **⚡ [Blitz 전략 매도]**
            - 🎯 **익절:** 진입가 +10% (${current_price*1.1:.2f})
            - 🛑 **손절:** 진입가 -15% (${current_price*0.85:.2f})
            """)

        # (선택) 거래량 설명 캡션
        st.caption("※ 거래량 강도: 당일 거래량 / 20일 평균. 1.5배 이상이면 '투매'로 간주하여 신뢰도 상승.")

    # =========================================================================
    # [PAGE 2] 백테스트 상세 분석 (승률 & 색상 적용)
    # =========================================================================
    elif menu == "📊 백테스트 상세 분석":
        st.title("📊 과거 신호 수익률 정밀 검증")
        st.markdown(f"최근 {check_years}년 데이터 기준 시뮬레이션입니다.")
        
        # --- 전체 시뮬레이션 데이터 생성 로직 (동일) ---
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
            
            # 등급 판별
            if cond_dia.iloc[i]: tier = "💎 다이아"
            elif cond_gold.iloc[i]: tier = "🥇 골드"
            elif cond_silver.iloc[i]: tier = "🥈 실버"
            elif cond_blitz.iloc[i]: tier = "⚡ 블리츠"
            else: tier = "기타"

            # 수익률 계산 (기존과 동일)
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
                "수익률(5일)": ret_5d,  # 숫자형 유지 (스타일링 위해)
                "15일후_주가": price_15d,
                "수익률(15일)": ret_15d # 숫자형 유지
            })

        if history:
            df_hist = pd.DataFrame(history)
            df_hist = df_hist.sort_values("날짜", ascending=False)

            # -----------------------------------------------------------------
            # 1. 승률(Win Rate) 통계 계산 및 표시 (신규 추가)
            # -----------------------------------------------------------------
            st.subheader("📈 전체 신호 승률 분석")
            
            # NaN 제외하고 계산
            valid_5d = df_hist.dropna(subset=['수익률(5일)'])
            valid_15d = df_hist.dropna(subset=['수익률(15일)'])
            
            # 승리 횟수 (수익률 > 0)
            win_5d = (valid_5d['수익률(5일)'] > 0).sum()
            win_15d = (valid_15d['수익률(15일)'] > 0).sum()
            
            # 승률 계산
            rate_5d = (win_5d / len(valid_5d) * 100) if len(valid_5d) > 0 else 0
            rate_15d = (win_15d / len(valid_15d) * 100) if len(valid_15d) > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("총 포착 신호", f"{len(df_hist)}회")
            with m2: st.metric("5일 후 승률 (익절)", f"{rate_5d:.1f}%")
            with m3: st.metric("15일 후 승률 (익절)", f"{rate_15d:.1f}%")
            
            st.markdown("---")

            # -----------------------------------------------------------------
            # 2. 상세 표 출력 (색상 스타일링 적용)
            # -----------------------------------------------------------------
            st.subheader("📋 신호 발생 이력 요약")
            
            # 화면 표시용 컬럼만 선택
            df_display = df_hist[['날짜', '등급', '매수가', '수익률(5일)', '수익률(15일)']].copy()
            
            # 색상 함수 정의 (빨강/파랑)
            def color_returns(val):
                if pd.isna(val): return ""
                color = '#ff4b4b' if val > 0 else '#4b88ff' # 빨강 / 파랑
                return f'color: {color}; font-weight: bold;'

            # Pandas Styler 적용
            st.dataframe(
                df_display.style
                .format({
                    "매수가": "${:.2f}",
                    "수익률(5일)": "{:+.2f}%",
                    "수익률(15일)": "{:+.2f}%"
                }, na_rep="-") # NaN은 '-'로 표시
                .map(color_returns, subset=['수익률(5일)', '수익률(15일)']), # 색상 적용
                use_container_width=True,
                hide_index=True
            )
            
            # -----------------------------------------------------------------
            # 3. 엑셀 다운로드
            # -----------------------------------------------------------------
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