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

P2E_URL = os.environ.get(
    "P2E_URL",
    "https://playtoearn.com/earn",
).strip()

# Always monitor these three Solana rewards.
TARGET_AMOUNTS = {
    "$2",
    "$5",
    "$10",
}

# The FREE $2 reward is specifically the 25-total pool.
FREE_STOCK_TOTAL = 25

STATE_FILE = Path(
    os.environ.get(
        "STATE_FILE",
        "reward_state.json",
    )
)

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "",
).strip()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> bool:
    """Send a Telegram message."""

    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing.")
        return False

    if not CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID is missing.")
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
# NORMALIZATION
# ============================================================

def normalize_amount(amount: str) -> str:
    """
    Convert reward amount into a standard form.

    Examples:

        $2
        $2.00
        $ 2

    become:

        $2
    """

    match = re.search(
        r"\$\s*(\d+(?:\.\d+)?)",
        amount.strip(),
    )

    if not match:
        raise ValueError(
            f"Invalid reward amount: {amount}"
        )

    number = float(match.group(1))

    if number.is_integer():
        return f"${int(number)}"

    return f"${number}"


def parse_stock(stock: str) -> tuple[int, int]:
    """
    Convert:

        3/25

    into:

        current = 3
        total = 25
    """

    match = re.fullmatch(
        r"\s*(\d+)\s*/\s*(\d+)\s*",
        stock,
    )

    if not match:
        raise ValueError(
            f"Invalid stock format: {stock}. "
            "Expected CURRENT/TOTAL, e.g. 3/25."
        )

    current = int(match.group(1))
    total = int(match.group(2))

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
# TARGET REWARD
# ============================================================

def is_target_reward(
    amount: str,
    total: int,
) -> bool:
    """
    Rules:

    $2:
        Monitor ONLY the free 25-total pool.

    $5:
        Monitor the Solana 10-total pool.

    $10:
        Monitor the Solana 5-total pool.

    Everything else:
        Ignore.
    """

    amount = normalize_amount(amount)

    if amount not in TARGET_AMOUNTS:
        return False

    if amount == "$2":
        return total == FREE_STOCK_TOTAL

    if amount == "$5":
        return total == 10

    if amount == "$10":
        return total == 5

    return False


def make_reward(
    amount: str,
    stock: str,
) -> dict[str, Any]:

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


# ============================================================
# REWARD KEY
# ============================================================

def reward_key(
    reward: dict[str, Any],
) -> str:
    """
    Create a unique key for each reward pool.
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
# STATE
# ============================================================

def load_state() -> dict[str, bool]:
    """Load previous availability state."""

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

        return {
            str(key): bool(value)
            for key, value in data.items()
        }

    except Exception as exc:

        print(
            "Could not read state file: "
            f"{type(exc).__name__}: {exc}"
        )

        return {}


def save_state(
    state: dict[str, bool],
) -> None:
    """Save availability state."""

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ============================================================
# ALERT MESSAGE
# ============================================================

def alert_message(
    reward: dict[str, Any],
) -> str:

    amount = reward["amount"]
    current = reward["current"]
    total = reward["total"]

    if (
        amount == "$2"
        and total == FREE_STOCK_TOTAL
    ):
        name = "$2 Solana FREE reward"
    else:
        name = f"{amount} Solana reward"

    return (
        "🚨 SOLANA REWARD AVAILABLE!\n\n"
        f"💰 {name}\n"
        f"📦 {current}/{total} available\n\n"
        "Redeem it manually on PlayToEarn:\n"
        f"{P2E_URL}"
    )


# ============================================================
# PROCESS REWARD
# ============================================================

def process_reward(
    reward: dict[str, Any],
    state: dict[str, bool],
) -> None:
    """
    Alert only on:

        unavailable → available

    No duplicate alert while it remains available.

    When it reaches zero:

        available → unavailable

    the state resets.

    Therefore:

        0/25
          ↓
        3/25  → ALERT
          ↓
        5/25  → NO ALERT
          ↓
        0/25  → RESET
          ↓
        4/25  → ALERT AGAIN
    """

    key = reward_key(reward)

    previous = state.get(
        key,
        False,
    )

    current = reward["available"]

    print(
        f"{reward['amount']} | "
        f"{reward['current']}/{reward['total']} | "
        f"available={current} | "
        f"previous={previous}"
    )

    if current and not previous:

        print(
            f"NEW REFILL DETECTED: "
            f"{reward['amount']} "
            f"{reward['current']}/"
            f"{reward['total']}"
        )

        send_telegram(
            alert_message(reward)
        )

    state[key] = current


# ============================================================
# LOCAL TEST
# ============================================================

def run_test() -> int:

    print("")
    print("===================================")
    print(" REWARD MONITOR LOCAL TEST")
    print("===================================")

    # Start with everything unavailable.
    state: dict[str, bool] = {}

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

    for number, scenario in enumerate(
        scenarios,
        start=1,
    ):

        print("")
        print(f"TEST {number}")

        for amount, stock in scenario.items():

            try:

                reward = make_reward(
                    amount,
                    stock,
                )

                process_reward(
                    reward,
                    state,
                )

            except ValueError as exc:

                print(
                    f"{amount} ignored: {exc}"
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

def test_telegram() -> int:

    success = send_telegram(
        "✅ Solana reward monitor "
        "Telegram test succeeded."
    )

    return 0 if success else 1


# ============================================================
# STATUS
# ============================================================

def show_status() -> int:

    state = load_state()

    print("")
    print("========== CURRENT STATE ==========")

    if not state:

        print(
            "No saved reward state."
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
# MANUAL CHECK
# ============================================================

def manual_check(
    values: list[str],
) -> int:

    state = load_state()

    print("")
    print("========== MANUAL CHECK ==========")

    processed = set()

    for value in values:

        if "=" not in value:

            print(
                f"Invalid input: {value}"
            )

            continue

        amount, stock = (
            value.split("=", 1)
        )

        try:

            reward = make_reward(
                amount,
                stock,
            )

        except ValueError as exc:

            print(
                f"Ignored {value}: {exc}"
            )

            continue

        key = reward_key(reward)

        processed.add(key)

        process_reward(
            reward,
            state,
        )

    # Anything not supplied in this check
    # is considered unavailable.
    for key in list(state.keys()):

        if key not in processed:
            state[key] = False

    save_state(state)

    print("==================================")
    print(
        f"State saved to {STATE_FILE}"
    )

    return 0


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Solana reward availability detector "
            "and Telegram notifier."
        )
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run the local detector test.",
    )

    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a Telegram test.",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show saved reward state.",
    )

    parser.add_argument(
        "--check",
        nargs="+",
        metavar="REWARD",
        help=(
            "Check reward values. "
            'Example: --check "$2=0/25" '
            '"$5=0/10" "$10=0/5"'
        ),
    )

    args = parser.parse_args()

    if args.test:
        return run_test()

    if args.test_telegram:
        return test_telegram()

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
