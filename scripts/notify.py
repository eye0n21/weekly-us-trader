"""
notify.py
주간 자동 알림 — data.json을 읽어 텔레그램으로 전송

환경변수:
  TELEGRAM_BOT_TOKEN  텔레그램 봇 토큰
  TELEGRAM_CHAT_ID    수신 채팅 ID
"""

import os
import sys
from typing import Optional

import requests

from shared import DATA_JSON, load_data as _load_data

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"[ERROR] 환경변수 {key} 가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)
    return val


def send_message(token: str, chat_id: str, text: str) -> None:
    """텔레그램 sendMessage API 호출 (MarkdownV2)."""
    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API 오류: {result}")


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

SEP = "━" * 22  # 3열 테이블(종목·비중·전주대비) 너비


def _delta_str(delta: float) -> str:
    """전주대비 문자열 (▲1.2% / ▼1.2% / ─0.0%)."""
    if delta > 0.05:
        return f"▲{delta:.1f}%"
    elif delta < -0.05:
        return f"▼{abs(delta):.1f}%"
    else:
        return "─"


def build_message(data: dict) -> str:
    week = data.get("week", "")
    deposit = data.get("deposit", 0)
    tickers = data.get("tickers", {})
    warnings = data.get("warnings", [])

    lines: list[str] = []

    # 헤더
    lines.append(f"📊 <b>[주간 매수 신호] {week}</b>")
    lines.append("")

    # 예수금 안내
    if deposit == 0:
        lines.append("⚠️ 예수금 미입력 — 비중만 표시합니다")
        lines.append("/calc [예수금] [현금비율%] 로 금액 계산")
        lines.append("예: <code>/calc 2670 28</code>")
    else:
        sys_ratio = data.get("sys_ratio", 0)
        disc_ratio = data.get("disc_ratio", 0)
        lines.append(
            f"예수금: <b>${deposit:,.0f}</b> | "
            f"Sys {sys_ratio*100:.1f}% / Disc {disc_ratio*100:.1f}%"
        )

    lines.append("")
    lines.append(SEP)
    lines.append(f"{'종목':<6}{'비중':>7}  {'전주대비':>8}")
    lines.append(SEP)

    # 종목별 행 (비중 내림차순)
    sorted_tickers = sorted(
        tickers.items(),
        key=lambda kv: kv[1].get("weight_pct", 0),
        reverse=True,
    )
    for ticker, info in sorted_tickers:
        weight = info.get("weight_pct", 0)
        delta = info.get("weight_delta", 0)
        lines.append(f"{ticker:<6}{weight:>6.1f}%  {_delta_str(delta):>8}")

    lines.append(SEP)

    # 경고
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"⚠️ {w}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = _get_env("TELEGRAM_BOT_TOKEN")
    chat_id = _get_env("TELEGRAM_CHAT_ID")

    data = _load_data()
    if data is None:
        print(f"[ERROR] {DATA_JSON} 파일이 없습니다. fetch_and_calc.py를 먼저 실행하세요.", file=sys.stderr)
        sys.exit(1)

    message = build_message(data)
    print("[MSG]")
    print(message)
    print()

    send_message(token, chat_id, message)
    masked = f"***{chat_id[-4:]}" if len(chat_id) > 4 else "****"
    print(f"[OK] 텔레그램 전송 완료 → chat_id={masked}")


if __name__ == "__main__":
    main()
