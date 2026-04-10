"""
bot.py
텔레그램 대화형 봇 — /calc 명령어로 매수 금액 계산

실행:
  python scripts/bot.py

환경변수:
  TELEGRAM_BOT_TOKEN  텔레그램 봇 토큰
  TELEGRAM_CHAT_ID    허용할 채팅 ID (보안용, 비워두면 전체 허용)
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DATA_JSON = ROOT / "docs" / "data" / "data.json"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SEP = "━" * 34

# ---------------------------------------------------------------------------
# 계산 헬퍼 (fetch_and_calc.py 와 동일 로직, 의존성 없이 자립)
# ---------------------------------------------------------------------------

def get_ratios(cash_ratio: float):
    if cash_ratio >= 0.4:
        return 0.055, 0.080
    elif cash_ratio >= 0.3:
        return 0.050, 0.075
    elif cash_ratio >= 0.2:
        return 0.045, 0.070
    else:
        return 0.040, 0.065


# ---------------------------------------------------------------------------
# 데이터 로딩
# ---------------------------------------------------------------------------

def load_data() -> Optional[dict]:
    if not DATA_JSON.exists():
        return None
    try:
        with DATA_JSON.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 메시지 빌더
# ---------------------------------------------------------------------------

def build_calc_message(data: dict, deposit: float, cash_ratio: float) -> str:
    sys_ratio, disc_ratio = get_ratios(cash_ratio)
    week = data.get("week", "")
    tickers = data.get("tickers", {})

    # 비중 내림차순 정렬
    sorted_tickers = sorted(
        tickers.items(),
        key=lambda kv: kv[1].get("weight_pct", 0),
        reverse=True,
    )

    lines: list[str] = []
    lines.append(f"💰 <b>[매수 계획] {week}</b>")
    lines.append(
        f"예수금: <b>${deposit:,.0f}</b> | 비율: {cash_ratio * 100:.0f}%"
    )
    lines.append(
        f"Systematic {sys_ratio * 100:.1f}% / Discretionary {disc_ratio * 100:.1f}%"
    )
    lines.append("")
    lines.append(SEP)
    lines.append(f"{'종목':<5} {'비중':>6}  {'본주매수':>9}  레버리지매수")
    lines.append(SEP)

    total_sys = 0.0
    total_disc = 0.0

    for ticker, info in sorted_tickers:
        weight = info.get("weight_pct", 0.0)
        dm = info.get("disc_multiplier", 0.0)
        lever = info.get("lever", "")

        sys_fund = deposit * sys_ratio * (weight / 100)
        disc_fund = deposit * disc_ratio * (weight / 100) * dm

        total_sys += sys_fund
        total_disc += disc_fund

        if dm > 0:
            lever_str = f"{lever} ${disc_fund:,.1f} [×{dm}]"
        else:
            lever_str = f"{lever} ─"

        lines.append(
            f"{ticker:<5} {weight:>5.1f}%  ${sys_fund:>8,.1f}  {lever_str}"
        )

    lines.append(SEP)
    lines.append(f"✅ 본주 합계:      ${total_sys:,.1f}")
    lines.append(f"✅ 레버리지 합계:  ${total_disc:,.1f}")
    lines.append(f"✅ 총 투자:        ${total_sys + total_disc:,.1f}")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"⚠️ {w}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 보안: 허용된 채팅 ID만 응답
# ---------------------------------------------------------------------------

ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_ID:
        return True  # 미설정 시 전체 허용
    return str(update.effective_chat.id) == ALLOWED_CHAT_ID


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    msg = (
        "📊 <b>Weekly US Trader Bot</b>\n\n"
        "사용 가능한 명령어:\n\n"
        "/calc [예수금] [현금비율%]\n"
        "  → 종목별 매수 금액 계산\n\n"
        "예시:\n"
        "<code>/calc 2670 28</code>\n"
        "  예수금 $2,670 / 현금비율 28%"
    )
    await update.message.reply_html(msg)


async def cmd_calc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return

    args = context.args

    # 인수 검증
    if len(args) != 2:
        await update.message.reply_html(
            "사용법: <code>/calc [예수금] [현금비율%]</code>\n"
            "예: <code>/calc 2670 28</code>"
        )
        return

    try:
        deposit = float(args[0].replace(",", ""))
        cash_ratio = float(args[1]) / 100
    except ValueError:
        await update.message.reply_text(
            "❌ 숫자를 입력해주세요.\n예: /calc 2670 28"
        )
        return

    if deposit <= 0:
        await update.message.reply_text("❌ 예수금은 0보다 커야 합니다.")
        return

    if not 0.0 <= cash_ratio <= 1.0:
        await update.message.reply_text(
            "❌ 현금비율은 0~100 사이 값을 입력해주세요."
        )
        return

    # 데이터 로드
    data = load_data()
    if data is None:
        await update.message.reply_text(
            "⚠️ 데이터 파일이 없습니다.\n"
            "GitHub Actions가 아직 실행되지 않았거나 파일을 찾을 수 없습니다."
        )
        return

    if not data.get("tickers"):
        await update.message.reply_text("⚠️ 종목 데이터가 비어 있습니다.")
        return

    msg = build_calc_message(data, deposit, cash_ratio)
    await update.message.reply_html(msg)
    logger.info(
        "calc: chat=%s deposit=%.0f cash_ratio=%.2f",
        update.effective_chat.id,
        deposit,
        cash_ratio,
    )


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(
            "[ERROR] TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("calc", cmd_calc))

    if not ALLOWED_CHAT_ID:
        logger.warning(
            "TELEGRAM_CHAT_ID 미설정 — 모든 사용자에게 응답합니다. "
            "운영 환경에서는 반드시 설정하세요."
        )
    else:
        logger.info("허용된 chat_id: ***%s", ALLOWED_CHAT_ID[-4:])

    logger.info("Bot polling started. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
