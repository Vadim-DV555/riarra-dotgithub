"""Тихие часы уведомлений: сейчас тихо или нет и границы последнего ночного окна.

Пишет quiet, since, until в $GITHUB_OUTPUT (since/until — ISO 8601 UTC).
Окно — с QUIET_FROM_HOUR вчера до QUIET_TO_HOUR сегодня по Москве.
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
QUIET_FROM_HOUR = 23
QUIET_TO_HOUR = 8


def window(now: datetime) -> tuple[bool, datetime, datetime]:
    """Тихо ли в момент now и последнее окно тишины, которое идёт или уже закончилось."""
    local = now.astimezone(MSK)
    quiet = local.hour >= QUIET_FROM_HOUR or local.hour < QUIET_TO_HOUR
    end_day = local.date() + timedelta(days=1) if local.hour >= QUIET_FROM_HOUR else local.date()
    since = datetime.combine(end_day - timedelta(days=1), time(QUIET_FROM_HOUR), MSK)
    until = datetime.combine(end_day, time(QUIET_TO_HOUR), MSK)
    return quiet, since, until


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    quiet, since, until = window(datetime.now(timezone.utc))
    lines = [f"quiet={'true' if quiet else 'false'}", f"since={iso_utc(since)}", f"until={iso_utc(until)}"]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    print(" ".join(lines), file=sys.stderr)


if __name__ == "__main__":
    main()
