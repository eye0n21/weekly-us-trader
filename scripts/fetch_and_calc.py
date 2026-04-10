"""
fetch_and_calc.py
주봉 데이터 수집 + 지표 계산 + docs/data/data.json 저장
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TICKER_PAIRS: Dict[str, str] = {
    "QQQ": "TQQQ", "NVDA": "NVDL", "AAPL": "AAPU",
    "GOOGL": "GGLL", "MSFT": "MSFU", "AMZN": "AMZU",
    "MSTR": "MSTX", "PLTR": "PLTU", "TSLA": "TSLL",
}

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
DATA_JSON = DATA_DIR / "data.json"

EMA_PERIOD = 240
RSI_PERIOD = 14
ATR_PERIOD = 14
MIN_WEEKS = 50
FETCH_PERIOD = "5y"

# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance가 MultiIndex 컬럼을 반환하는 경우 단일 레벨로 평탄화."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def compute_ema(series: pd.Series, period: int = EMA_PERIOD) -> float:
    """
    EMA 계산. 가용 데이터가 period 미만이면 있는 만큼만 span으로 사용.
    """
    span = min(len(series), period)
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def compute_rsi(series: pd.Series, period: int = RSI_PERIOD) -> float:
    """Wilder 방식 RSI(period)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return float((100 - 100 / (1 + rs)).iloc[-1])


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    """Wilder 방식 ATR(period)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.ewm(com=period - 1, min_periods=period).mean().iloc[-1])


# ---------------------------------------------------------------------------
# Multiplier lookup tables
# ---------------------------------------------------------------------------

def rsi_mult(rsi: float) -> float:
    if rsi < 40:
        return 2.0
    elif rsi < 50:
        return 1.5
    elif rsi < 60:
        return 1.0
    elif rsi < 70:
        return 0.8
    else:
        return 0.5


def trend_mult(divergence: float) -> float:
    if divergence > 60:
        return 0.8
    elif divergence > 30:
        return 1.0
    elif divergence > 0:
        return 1.2
    else:
        return 1.5


def disc_multiplier(divergence: float) -> float:
    if divergence <= -5:
        return 1.5
    elif divergence <= 5:
        return 1.2
    elif divergence <= 15:
        return 0.7
    elif divergence <= 30:
        return 0.5
    else:
        return 0.0


def get_ratios(cash_ratio: float) -> Tuple[float, float]:
    """cash_ratio에 따라 (sys_ratio, disc_ratio) 반환."""
    if cash_ratio >= 0.4:
        return 0.055, 0.080
    elif cash_ratio >= 0.3:
        return 0.050, 0.075
    elif cash_ratio >= 0.2:
        return 0.045, 0.070
    else:
        return 0.040, 0.065


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_weekly_ohlcv(ticker: str) -> Optional[pd.DataFrame]:
    """최대 5년치 주봉 OHLCV 수집. 실패 시 None 반환."""
    try:
        df = yf.download(
            ticker,
            period=FETCH_PERIOD,
            interval="1wk",
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return None
        df = _flatten_columns(df)
        return df.dropna(subset=["Close"])
    except Exception as exc:
        print(f"[WARN] {ticker} 주봉 수집 실패: {exc}")
        return None


def fetch_latest_price(ticker: str) -> Optional[float]:
    """레버리지 ETF 최근 종가 수집."""
    try:
        df = yf.download(
            ticker,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return None
        df = _flatten_columns(df)
        return float(df["Close"].dropna().iloc[-1])
    except Exception as exc:
        print(f"[WARN] {ticker} 레버 가격 수집 실패: {exc}")
        return None


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_previous_weights() -> Dict[str, float]:
    """기존 data.json에서 weight_pct 읽기 (전주 비교용)."""
    if not DATA_JSON.exists():
        return {}
    try:
        with DATA_JSON.open(encoding="utf-8") as f:
            prev = json.load(f)
        return {
            ticker: info.get("weight_pct", 0.0)
            for ticker, info in prev.get("tickers", {}).items()
        }
    except Exception:
        return {}


def iso_week_label() -> str:
    """현재 UTC 기준 ISO 주차 레이블 반환 (예: '2025-W14')."""
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def run(deposit: float = 0.0, cash_ratio: float = 0.0) -> dict:
    """
    전 종목 지표 계산 후 data.json / data_YYYY-WNN.json 저장.

    Parameters
    ----------
    deposit    : 총 투자 원금 (KRW 또는 USD). 기본값 0 — 나중에 /calc 명령으로 주입.
    cash_ratio : 현금 비율 (0.0–1.0). 기본값 0.
    """
    warnings: list = []
    prev_weights = load_previous_weights()
    sys_ratio, disc_ratio = get_ratios(cash_ratio)
    week_label = iso_week_label()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1차 패스: 지표 계산 + 이상 감지
    ticker_data: Dict[str, dict] = {}
    raw_scores: Dict[str, float] = {}

    for base, lever in TICKER_PAIRS.items():
        df = fetch_weekly_ohlcv(base)

        # --- 이상 감지 ---
        n_weeks = len(df) if df is not None else 0
        if df is None or n_weeks < MIN_WEEKS:
            warnings.append(
                f"{base}: 데이터 부족 ({n_weeks}주 < {MIN_WEEKS}주 기준) — 제외됨"
            )
            continue

        close = df["Close"]
        ema_val = compute_ema(close)
        rsi_val = compute_rsi(close)
        atr_val = compute_atr(df)

        if any(math.isnan(v) for v in (ema_val, rsi_val, atr_val)):
            warnings.append(f"{base}: 지표 NaN 감지 — 제외됨")
            continue

        last_close = float(close.iloc[-1])
        atr_pct = (atr_val / last_close) * 100
        divergence = (last_close - ema_val) / ema_val * 100

        rm = rsi_mult(rsi_val)
        tm = trend_mult(divergence)
        dm = disc_multiplier(divergence)
        raw = (1 / atr_pct) ** 1.2 * rm ** 1.0 * tm ** 1.4

        lever_price = fetch_latest_price(lever)
        raw_scores[base] = raw

        ticker_data[base] = {
            "close": round(last_close, 4),
            "ema": round(ema_val, 4),
            "rsi": round(rsi_val, 4),
            "atr": round(atr_val, 4),
            "atr_pct": round(atr_pct, 4),
            "divergence": round(divergence, 4),
            "rsi_mult": rm,
            "trend_mult": tm,
            "raw_score": round(raw, 6),
            # 2차 패스에서 채워짐
            "weight_pct": 0.0,
            "weight_delta": 0.0,
            "systematic_fund": 0.0,
            "discretionary_fund": 0.0,
            "lever": lever,
            "lever_price": round(lever_price, 4) if lever_price is not None else None,
            "disc_multiplier": dm,
        }

    # 2차 패스: 비중 정규화 + 매수금액 계산
    total_raw = sum(raw_scores.values())
    for base, raw in raw_scores.items():
        weight = (raw / total_raw) * 100
        prev_w = prev_weights.get(base, 0.0)

        systematic_fund = deposit * sys_ratio * (weight / 100)
        base_disc_fund = deposit * disc_ratio * (weight / 100)
        dm = ticker_data[base]["disc_multiplier"]
        discretionary_fund = base_disc_fund * dm

        ticker_data[base].update(
            {
                "weight_pct": round(weight, 4),
                "weight_delta": round(weight - prev_w, 4),
                "systematic_fund": round(systematic_fund, 2),
                "discretionary_fund": round(discretionary_fund, 2),
            }
        )

    result = {
        "generated_at": generated_at,
        "week": week_label,
        "deposit": deposit,
        "cash_ratio": cash_ratio,
        "sys_ratio": sys_ratio,
        "disc_ratio": disc_ratio,
        "tickers": ticker_data,
        "warnings": warnings,
    }

    # 저장
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with DATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    history_path = DATA_DIR / f"data_{week_label}.json"
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] {week_label} 저장 완료 → {DATA_JSON}")
    print(f"[OK] 히스토리 저장 → {history_path}")
    if warnings:
        print("[WARN] 이상 감지:")
        for w in warnings:
            print(f"  - {w}")

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Weekly US stock scorer")
    parser.add_argument(
        "--deposit", type=float, default=0.0,
        help="총 투자 원금 (기본값 0 — 나중에 /calc로 주입)",
    )
    parser.add_argument(
        "--cash-ratio", type=float, default=0.0,
        help="현금 비율 0.0–1.0 (기본값 0)",
    )
    args = parser.parse_args()

    if args.deposit < 0:
        parser.error("--deposit 는 0 이상이어야 합니다.")
    if not 0.0 <= args.cash_ratio <= 1.0:
        parser.error("--cash-ratio 는 0.0~1.0 사이여야 합니다.")

    output = run(deposit=args.deposit, cash_ratio=args.cash_ratio)
    print(json.dumps(output, ensure_ascii=False, indent=2))
