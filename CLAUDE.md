# CLAUDE.md — weekly-us-trader

**스택**: yfinance → 지표 계산 → 텔레그램 알림 + GitHub Pages 대시보드
**실행**: 매주 화요일 06:00 UTC (GitHub Actions)

## NEVER DO
- EMA span을 240 고정하지 않는다 — `min(240, len(df))` 로 계산
- 레버리지 ETF로 지표 계산하지 않는다 — 본주만
- TICKER_PAIRS 임의 변경 금지
- `deposit`, `cash_ratio`, 텔레그램 토큰/ID 하드코딩 금지 — 환경변수만

## 종목 페어 (고정)
```python
TICKER_PAIRS = {
    "QQQ":"TQQQ", "NVDA":"NVDL", "AAPL":"AAPU", "GOOGL":"GGLL",
    "MSFT":"MSFU", "AMZN":"AMZU", "MSTR":"MSTX", "PLTR":"PLTU", "TSLA":"TSLL"
}
```

## 수식 (변경 금지)
```
EMA        = ewm(span=min(240, len))
RSI(14), ATR(14), ATR_Pct = ATR/Close*100
Divergence = (Close-EMA)/EMA*100

RSI_Mult : <40→2.0, <50→1.5, <60→1.0, <70→0.8, >=70→0.5
Trend_Mult: div>60→0.8, >30→1.0, >0→1.2, else→1.5

raw_score  = (1/ATR_Pct)^1.2 * RSI_Mult * Trend_Mult^1.4
weight_pct = raw_score / sum * 100

cash_ratio: >=0.4→sys5.5/disc8.0, >=0.3→5.0/7.5, >=0.2→4.5/7.0, else→4.0/6.5
sys_fund   = deposit * sys_ratio * weight/100
disc base  = deposit * disc_ratio * weight/100
disc_mult  : div<=-5→1.5, <=5→1.2, <=15→0.7, <=30→0.5, else→0
```

## data.json 키
`generated_at, week, deposit, cash_ratio, sys_ratio, disc_ratio, warnings`
ticker 필드: `close, ema, rsi, atr, atr_pct, divergence, rsi_mult, trend_mult, raw_score, weight_pct, weight_delta, systematic_fund, discretionary_fund, lever, lever_price, disc_multiplier`

## 개발 현황
- [x] A-1 `fetch_and_calc.py` — 데이터 수집 + 지표 계산
- [x] A-2 `notify.py` — 텔레그램 주간 알림
- [x] A-3 `update.yml` — GitHub Actions
- [x] A-4 `bot.py` — /calc 텔레그램 봇
- [x] B-1 `index.html` — 수치 표
- [x] B-2 Weight% 바 차트
- [x] B-3 인터랙티브 계산기
- [x] B-4 본주 vs 레버리지 비교 표
- [x] B-5 누적 Weight% 히스토리 차트
