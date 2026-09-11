import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import requests


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_P2E_URL = "https://playtoearn.com/earn"
DEFAULT_STATE_FILE = "reward_state.json"

P2E_URL = os.environ.get(
    "P2E_URL",
    DEFAULT_P2E_URL,
).strip()

TARGET_AMOUNTS = [
    x.strip().lower()
    for x in os.environ.get(
        "TARGET_AMOUNTS",
        "$2,$5,$10",
    ).split(",")
    if x.strip()
]

try:
    FREE_STOCK_TOTAL = int(
        os.environ.get(
            "FREE_STOCK_TOTAL",
            "25",
        )
    )
except ValueError:
    FREE_STOCK_TOTAL = 25

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "",
).strip()

STATE_FILE = Path(
    os.environ.get(
        "STATE_FILE",
        DEFAULT_STATE_FILE,
    )
)


# ============================================================
# TELEGRAM
# ============================================================

def telegram(message: str) -> bool:
    """
    Send a Telegram message.

    TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    must be provided through environment variables.
    """

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram is not configured.")
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=20,
        )

        response.raise_for_status()

        print("Telegram notification sent.")
        return True

    except Exception as exc:
        print(
            "Telegram error: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


# ============================================================
# STATE
# ============================================================

def load_state() -> dict[str, bool]:
    """
    Load previous availability state.

    Example:

    {
        "$2-free-25": true,
        "$5-10": false,
        "$10-5": true
    }
    """

    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return {}

        result = {}

        for key, value in data.items():
            result[str(key)] = bool(value)

        return result

    except Exception as exc:
        print(
            "Could not load state file: "
            f"{type(exc).__name__}: {exc}"
        )

        return {}


def save_state(
    state: dict[str, bool],
) -> None:
    """
    Save availability state.
    """

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ============================================================
# REWARD PARSING
# ============================================================

def normalize_amount(
    amount: str,
) -> str:
    """
    Normalize:

        $2
        $2.00
        $ 2

    into:

        $2
    """

    match = re.search(
        r"\$\s*(\d+(?:\.\d+)?)",
        amount,
    )

    if not match:
        raise ValueError(
            f"Invalid reward amount: {amount}"
        )

    number = float(match.group(1))

    if number.is_integer():
        return f"${int(number)}".lower()

    return f"${number}".lower()


def parse_stock(
    stock: str,
) -> tuple[int, int]:
    """
    Parse:

        3/25

    into:

        (3, 25)
    """

    stock = stock.strip()

    match = re.fullmatch(
        r"(\d+)\s*/\s*(\d+)",
        stock,
    )

    if not match:
        raise ValueError(
            "Stock must use the format CURRENT/TOTAL. "
            "Example: 3/25"
        )

    current = int(match.group(1))
    total = int(match.group(2))

    if current < 0:
        raise ValueError(
            "Current stock cannot be negative."
        )

    if total <= 0:
        raise ValueError(
            "Total stock must be greater than zero."
        )

    if current > total:
        raise ValueError(
            "Current stock cannot be greater than total."
        )

    return current, total


# ============================================================
# TARGET FILTERING
# ============================================================

def is_target_reward(
    amount: str,
    total: int,
) -> bool:
    """
    Decide whether a reward should be monitored.

    Rules:

    $2:
        Only total=25.
        This is the FREE $2 pool.

    $5:
        Solana $5 pool.

    $10:
        Solana $10 pool.

    Other rewards:
        Ignore.
    """

    amount = normalize_amount(amount)

    if amount not in TARGET_AMOUNTS:
        return False

    if amount == "$2":
        return total == FREE_STOCK_TOTAL

    return amount in {
        "$5",
        "$10",
    }


# ============================================================
# REWARD OBJECT
# ============================================================

def create_reward(
    amount: str,
    stock: str,
) -> dict[str, Any]:
    """
    Create a normalized reward object.
    """

    amount = normalize_amount(amount)

    current, total = parse_stock(stock)

    if not is_target_reward(
        amount,
        total,
    ):
        raise ValueError(
            f"{amount} {current}/{total} "
            "is not a monitored reward."
        )

    return {
        "amount": amount,
        "current": current,
        "total": total,
        "available": current > 0,
    }


def reward_key(
    reward: dict[str, Any],
) -> str:
    """
    Unique key for each reward pool.

    Examples:

        $2-free-25
        $5-10
        $10-5
    """

    amount = reward["amount"]
    total = reward["total"]

    if (
        amount == "$2"
        and total == FREE_STOCK_TOTAL
    ):
        return "$2-free-25"

    return f"{amount}-{total}"


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def build_alert_message(
    reward: dict[str, Any],
) -> str:
    """
    Build the refill notification.
    """

    amount = reward["amount"]
    current = reward["current"]
    total = reward["total"]

    if (
        amount == "$2"
        and total == FREE_STOCK_TOTAL
    ):
        reward_name = "$2 Solana FREE reward"

    else:
        reward_name = (
            f"{amount} Solana reward"
        )

    return (
        "🚨 SOLANA REWARD AVAILABLE!\n\n"
        f"💰 {reward_name}\n"
        f"📦 {current} / {total} available\n\n"
        "Open PlayToEarn NOW and redeem manually:\n"
        f"{P2E_URL}"
    )


# ============================================================
# PROCESS REWARD
# ============================================================

def process_reward(
    reward: dict[str, Any],
    state: dict[str, bool],
) -> bool:
    """
    Process one reward.

    Alert only when:

        unavailable → available

    Examples:

        0/25 → 3/25  = ALERT
        3/25 → 5/25  = NO ALERT
        5/25 → 0/25  = RESET
        0/25 → 4/25  = ALERT AGAIN
    """

    key = reward_key(reward)

    current_available = bool(
        reward["available"]
    )

    old_available = bool(
        state.get(key, False)
    )

    print(
        f"{reward['amount']} | "
        f"{reward['current']}/{reward['total']} | "
        f"available={current_available} | "
        f"previous={old_available}"
    )

    sent = False

    # --------------------------------------------------------
    # NEW REFILL
    # --------------------------------------------------------

    if (
        current_available
        and not old_available
    ):
        print(
            f"NEW REFILL DETECTED: "
            f"{reward['amount']} "
            f"{reward['current']}/"
            f"{reward['total']}"
        )

        sent = telegram(
            build_alert_message(
                reward
            )
        )

    # --------------------------------------------------------
    # UPDATE STATE
    # --------------------------------------------------------

    state[key] = current_available

    return sent


# ============================================================
# MANUAL CHECK
# ============================================================

def manual_check(
    values: list[str],
) -> int:
    """
    Manually provide reward values.

    Example:

        python monitor.py --check \
            "$2=0/25" \
            "$5=0/10" \
            "$10=0/5"

    """

    state = load_state()

    print("")
    print("========== REWARD CHECK ==========")

    processed_keys = set()

    for value in values:

        if "=" not in value:
            print(
                f"Invalid value: {value}"
            )
            continue

        amount_text, stock = (
            value.split("=", 1)
        )

        try:

            reward = create_reward(
                amount_text,
                stock,
            )

        except ValueError as exc:

            print(
                f"Ignored {value}: {exc}"
            )

            continue

        key = reward_key(reward)

        processed_keys.add(key)

        process_reward(
            reward,
            state,
        )

    # --------------------------------------------------------
    # Missing rewards are considered unavailable.
    # This allows a later refill to trigger again.
    # --------------------------------------------------------

    for key in list(state.keys()):

        if key not in processed_keys:

            state[key] = False

    save_state(state)

    print("===================================")
    print("")
    print(
        f"State saved to: {STATE_FILE}"
    )

    return 0


# ============================================================
# TEST SCENARIO
# ============================================================

def run_test() -> int:
    """
    Run a complete local test.

    This does NOT access PlayToEarn.

    It tests:

        0 → positive
        positive → positive
        positive → 0
        0 → positive again
    """

    print("")
    print("===================================")
    print(" REWARD MONITOR LOCAL TEST")
    print("===================================")

    state = {}

    scenarios = [
        {
            "$2": "0/25",
            "$5": "0/10",
            "$10": "0/5",
        },
        {
            "$2": "3/25",
            "$5": "0/10",
            "$10": "0/5",
        },
        {
            "$2": "5/25",
            "$5": "2/10",
            "$10": "0/5",
        },
        {
            "$2": "0/25",
            "$5": "4/10",
            "$10": "1/5",
        },
        {
            "$2": "4/25",
            "$5": "0/10",
            "$10": "0/5",
        },
    ]

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):

        print("")
        print(
            f"TEST {index}"
        )

        for amount, stock in scenario.items():

            try:

                reward = create_reward(
                    amount,
                    stock,
                )

                process_reward(
                    reward,
                    state,
                )

            except ValueError as exc:

                print(
                    f"{amount} ignored: "
                    f"{exc}"
                )

    print("")
    print("Final state:")
    print(
        json.dumps(
            state,
            indent=2,
        )
    )

    print("")
    print(
        "Local detector test completed."
    )

    return 0


# ============================================================
# TELEGRAM TEST
# ============================================================

def telegram_test() -> int:
    """
    Send a Telegram test message.
    """

    ok = telegram(
        "✅ Solana reward monitor "
        "Telegram test succeeded.\n\n"
        "The bot can send refill alerts."
    )

    return 0 if ok else 1


# ============================================================
# STATUS
# ============================================================

def show_status() -> int:
    """
    Show current stored reward state.
    """

    state = load_state()

    print("")
    print("========== CURRENT STATE ==========")

    if not state:
        print(
            "No reward state has been recorded yet."
        )

    else:

        for key, value in sorted(
            state.items()
        ):
            print(
                f"{key}: available={value}"
            )

    print("===================================")

    return 0


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Personal Solana reward "
            "availability notifier."
        )
    )

    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help=(
            "Send a Telegram test message."
        ),
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Run the local reward detector test."
        ),
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Show the current saved reward state."
        ),
    )

    parser.add_argument(
        "--check",
        nargs="+",
        metavar="REWARD",
        help=(
            "Check manually supplied rewards. "
            "Example: "
            '--check "$2=0/25" "$5=0/10" "$10=0/5"'
        ),
    )

    args = parser.parse_args()

    if args.test_telegram:
        return telegram_test()

    if args.test:
        return run_test()

    if args.status:
        return show_status()

    if args.check:
        return manual_check(
            args.check
        )

    parser.print_help()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
