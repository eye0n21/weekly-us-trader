"""
shared.py
여러 스크립트가 공유하는 경로 상수 · 순수 계산 함수 · 데이터 로더
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

DATA_DIR: Path = Path(__file__).parent.parent / "docs" / "data"
DATA_JSON: Path = DATA_DIR / "data.json"


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


def load_data() -> Optional[dict]:
    """data.json을 읽어 반환. 파일 없음 / JSON 파싱 실패 시 None."""
    try:
        with DATA_JSON.open(encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
