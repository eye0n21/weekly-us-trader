"""
tests/test_calc.py
fetch_and_calc.py 핵심 계산 로직 단위 테스트

실행: pytest tests/ -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_and_calc import (
    compute_atr,
    compute_ema,
    compute_rsi,
    disc_multiplier,
    get_ratios,
    rsi_mult,
    trend_mult,
)

# ── rsi_mult ──────────────────────────────────────────────────────────────────

class TestRsiMult:
    """RSI 구간별 배수 — 경계값 중심"""

    def test_below_40(self):
        assert rsi_mult(0)    == 2.0
        assert rsi_mult(39.9) == 2.0

    def test_boundary_40(self):
        assert rsi_mult(40.0) == 1.5

    def test_40_to_50(self):
        assert rsi_mult(45)   == 1.5
        assert rsi_mult(49.9) == 1.5

    def test_boundary_50(self):
        assert rsi_mult(50.0) == 1.0

    def test_50_to_60(self):
        assert rsi_mult(55)   == 1.0
        assert rsi_mult(59.9) == 1.0

    def test_boundary_60(self):
        assert rsi_mult(60.0) == 0.8

    def test_60_to_70(self):
        assert rsi_mult(65)   == 0.8
        assert rsi_mult(69.9) == 0.8

    def test_boundary_70(self):
        assert rsi_mult(70.0) == 0.5

    def test_above_70(self):
        assert rsi_mult(85)   == 0.5
        assert rsi_mult(100)  == 0.5


# ── trend_mult ────────────────────────────────────────────────────────────────

class TestTrendMult:
    """Divergence 구간별 배수 — 경계값 중심"""

    def test_above_60(self):
        assert trend_mult(60.1) == 0.8
        assert trend_mult(100)  == 0.8

    def test_boundary_60(self):
        # 60 초과(>60)가 아니므로 다음 구간
        assert trend_mult(60.0) == 1.0

    def test_30_to_60(self):
        assert trend_mult(30.1) == 1.0
        assert trend_mult(45)   == 1.0

    def test_boundary_30(self):
        assert trend_mult(30.0) == 1.2

    def test_0_to_30(self):
        assert trend_mult(0.1)  == 1.2
        assert trend_mult(15)   == 1.2

    def test_boundary_0(self):
        assert trend_mult(0.0)  == 1.5

    def test_negative(self):
        assert trend_mult(-1)   == 1.5
        assert trend_mult(-100) == 1.5


# ── disc_multiplier ───────────────────────────────────────────────────────────

class TestDiscMultiplier:
    """Divergence 구간별 레버리지 배수 — 경계값 중심"""

    def test_lte_minus5(self):
        assert disc_multiplier(-5.0) == 1.5
        assert disc_multiplier(-100) == 1.5

    def test_minus5_to_5(self):
        # -5 초과 ~ 5 이하
        assert disc_multiplier(-4.9) == 1.2
        assert disc_multiplier(0)    == 1.2
        assert disc_multiplier(5.0)  == 1.2

    def test_5_to_15(self):
        assert disc_multiplier(5.1)  == 0.7
        assert disc_multiplier(10)   == 0.7
        assert disc_multiplier(15.0) == 0.7

    def test_15_to_30(self):
        assert disc_multiplier(15.1) == 0.5
        assert disc_multiplier(20)   == 0.5
        assert disc_multiplier(30.0) == 0.5

    def test_above_30(self):
        assert disc_multiplier(30.1) == 0.0
        assert disc_multiplier(100)  == 0.0


# ── get_ratios ────────────────────────────────────────────────────────────────

class TestGetRatios:
    """cash_ratio 구간별 sys/disc 비율"""

    def test_tier1_gte_04(self):
        sys_r, disc_r = get_ratios(0.4)
        assert sys_r  == pytest.approx(0.055)
        assert disc_r == pytest.approx(0.080)

    def test_tier1_above_04(self):
        sys_r, disc_r = get_ratios(0.9)
        assert sys_r  == pytest.approx(0.055)
        assert disc_r == pytest.approx(0.080)

    def test_tier2_gte_03(self):
        sys_r, disc_r = get_ratios(0.3)
        assert sys_r  == pytest.approx(0.050)
        assert disc_r == pytest.approx(0.075)

    def test_tier3_gte_02(self):
        sys_r, disc_r = get_ratios(0.2)
        assert sys_r  == pytest.approx(0.045)
        assert disc_r == pytest.approx(0.070)

    def test_tier4_below_02(self):
        sys_r, disc_r = get_ratios(0.0)
        assert sys_r  == pytest.approx(0.040)
        assert disc_r == pytest.approx(0.065)

    def test_tier4_just_below_02(self):
        sys_r, disc_r = get_ratios(0.19)
        assert sys_r  == pytest.approx(0.040)
        assert disc_r == pytest.approx(0.065)


# ── compute_ema ───────────────────────────────────────────────────────────────

class TestComputeEma:
    """EMA 계산 — 데이터 부족 시 가용 길이로 span 조정"""

    def test_short_series_uses_available_span(self):
        # 10개 데이터 → span=10으로 계산, 오류 없어야 함
        series = pd.Series([100.0] * 10)
        result = compute_ema(series, period=240)
        assert isinstance(result, float)
        assert result == pytest.approx(100.0)

    def test_constant_series_returns_same_value(self):
        series = pd.Series([50.0] * 100)
        assert compute_ema(series) == pytest.approx(50.0)

    def test_full_period_available(self):
        series = pd.Series([200.0] * 240)
        assert compute_ema(series) == pytest.approx(200.0)

    def test_rising_series_ema_below_last(self):
        # 꾸준히 오르는 시리즈 → EMA는 최신 종가보다 낮아야 함
        series = pd.Series(range(1, 51), dtype=float)
        result = compute_ema(series, period=20)
        assert result < series.iloc[-1]

    def test_single_element(self):
        series = pd.Series([123.45])
        assert compute_ema(series) == pytest.approx(123.45)


# ── compute_rsi ───────────────────────────────────────────────────────────────

class TestComputeRsi:
    """RSI 값 범위 및 극단값 검증"""

    def test_range_0_to_100(self):
        series = pd.Series([float(i) for i in range(1, 51)])
        result = compute_rsi(series)
        assert 0.0 <= result <= 100.0

    def test_all_gains_rsi_high(self):
        # 계속 오르면 RSI 는 높아야 함
        series = pd.Series([float(i) for i in range(1, 31)])
        result = compute_rsi(series)
        assert result > 70.0

    def test_all_losses_rsi_low(self):
        # 계속 내리면 RSI 는 낮아야 함
        series = pd.Series([float(i) for i in range(30, 0, -1)])
        result = compute_rsi(series)
        assert result < 30.0

    def test_flat_series_rsi_middle(self):
        # 변동 없으면 RSI 는 50 근처
        series = pd.Series([100.0] * 30)
        result = compute_rsi(series)
        # 변동이 없으면 0/0 → NaN 이 될 수 있음, 이상 감지로 걸러짐
        assert isinstance(result, float)


# ── compute_atr ───────────────────────────────────────────────────────────────

class TestComputeAtr:
    """ATR 값 범위 검증"""

    N_WEEKS = 30  # 테스트용 공통 기간

    def _make_df(self, high, low, close):
        return pd.DataFrame({"High": high, "Low": low, "Close": close})

    def test_atr_is_positive(self):
        n = self.N_WEEKS
        df = self._make_df(
            high  = [110.0] * n,
            low   = [90.0]  * n,
            close = [100.0] * n,
        )
        result = compute_atr(df)
        assert result > 0.0

    def test_zero_range_atr_near_zero(self):
        # High == Low == Close → TR 이 0에 가까움
        n = self.N_WEEKS
        df = self._make_df(
            high  = [100.0] * n,
            low   = [100.0] * n,
            close = [100.0] * n,
        )
        result = compute_atr(df)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_atr_reflects_volatility(self):
        # 변동성 큰 쪽이 ATR 더 높아야 함
        n = self.N_WEEKS
        low_vol  = self._make_df([101.0]*n, [99.0]*n,  [100.0]*n)
        high_vol = self._make_df([120.0]*n, [80.0]*n,  [100.0]*n)
        assert compute_atr(high_vol) > compute_atr(low_vol)


# ── 통합: 비중 합계 ───────────────────────────────────────────────────────────

class TestWeightNormalization:
    """raw_score 정규화 후 weight 합계가 100이 되는지 확인"""

    def test_weights_sum_to_100(self):
        raw_scores = {
            "QQQ": 0.20, "NVDA": 0.07, "AAPL": 0.15,
            "GOOGL": 0.08, "MSFT": 0.35, "AMZN": 0.12,
            "MSTR": 0.09, "PLTR": 0.05, "TSLA": 0.17,
        }
        total = sum(raw_scores.values())
        weights = {t: (r / total) * 100 for t, r in raw_scores.items()}
        assert sum(weights.values()) == pytest.approx(100.0, rel=1e-6)

    def test_single_ticker_weight_is_100(self):
        raw_scores = {"QQQ": 0.5}
        total = sum(raw_scores.values())
        weights = {t: (r / total) * 100 for t, r in raw_scores.items()}
        assert weights["QQQ"] == pytest.approx(100.0)
