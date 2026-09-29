"""Утренняя сводка в Telegram: что случилось в репозитории за тихие часы.

Ночью _notify-pr, _notify-push и _notify-issue молчат (см. actions/quiet-hours),
а этот скрипт утром одним сообщением перечисляет PR, коммиты в основную ветку
и задачи за окно [SINCE, UNTIL). Пустая ночь — сообщения нет.

Окружение: REPO, GITHUB_TOKEN, BOT_TOKEN, CHAT_ID, SINCE, UNTIL (ISO 8601 UTC).
"""
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

GITHUB_API = "https://api.github.com"
TELEGRAM_API = "https://api.telegram.org"
PER_PAGE = 100
MAX_PAGES = 5
MAX_ITEMS_PER_SECTION = 15
TELEGRAM_TEXT_LIMIT = 4096
REQUEST_TIMEOUT = 30


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def github_get(path: str, token: str, params: dict) -> list:
    url = f"{GITHUB_API}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.load(response)


def in_window(value: str | None, since: datetime, until: datetime) -> bool:
    moment = parse_ts(value)
    return moment is not None and since <= moment < until


def link(url: str, text: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>'


def pull_lines(repo: str, token: str, since: datetime, until: datetime) -> list[str]:
    lines = []
    for page in range(1, MAX_PAGES + 1):
        pulls = github_get(f"/repos/{repo}/pulls", token, {
            "state": "all", "sort": "updated", "direction": "desc",
            "per_page": PER_PAGE, "page": page,
        })
        for pr in pulls:
            title = f"#{pr['number']} {pr['title']}"
            if in_window(pr["merged_at"], since, until):
                lines.append(f"🎉 смёржен {link(pr['html_url'], title)}")
            elif in_window(pr["closed_at"], since, until):
                lines.append(f"❌ закрыт {link(pr['html_url'], title)}")
            if in_window(pr["created_at"], since, until):
                lines.append(f"🔀 открыт {link(pr['html_url'], title)}")
        if len(pulls) < PER_PAGE or parse_ts(pulls[-1]["updated_at"]) < since:
            break
    return lines


def commit_lines(repo: str, token: str, branch: str, since: datetime, until: datetime) -> list[str]:
    commits = github_get(f"/repos/{repo}/commits", token, {
        "sha": branch, "per_page": PER_PAGE,
        "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "until": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    return [
        f"<code>{c['sha'][:7]}</code> {link(c['html_url'], c['commit']['message'].splitlines()[0])}"
        for c in commits
    ]


def issue_lines(repo: str, token: str, since: datetime, until: datetime) -> list[str]:
    issues = github_get(f"/repos/{repo}/issues", token, {
        "state": "all", "per_page": PER_PAGE, "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    lines = []
    for issue in issues:
        if "pull_request" in issue:
            continue
        title = f"#{issue['number']} {issue['title']}"
        if in_window(issue["created_at"], since, until):
            lines.append(f"🆕 открыта {link(issue['html_url'], title)}")
        if in_window(issue["closed_at"], since, until):
            lines.append(f"✅ закрыта {link(issue['html_url'], title)}")
    return lines


def section(header: str, lines: list[str]) -> str:
    shown = lines[:MAX_ITEMS_PER_SECTION]
    rest = len(lines) - len(shown)
    tail = [f"…и ещё {rest}"] if rest else []
    return "\n".join([f"<b>{header}: {len(lines)}</b>", *shown, *tail])


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "parse_mode": "HTML",
        "disable_web_page_preview": "true", "text": text,
    }).encode()
    request = urllib.request.Request(f"{TELEGRAM_API}/bot{bot_token}/sendMessage", data=data)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        response.read()


def main() -> None:
    env = os.environ
    if not env.get("BOT_TOKEN") or not env.get("CHAT_ID"):
        print("No NOTIFY_BOT_TOKEN / NOTIFY_CHAT_ID — skipping", file=sys.stderr)
        return
    repo, token = env["REPO"], env["GITHUB_TOKEN"]
    since, until = parse_ts(env["SINCE"]), parse_ts(env["UNTIL"])
    branch = env["DEFAULT_BRANCH"]

    sections = [
        ("PR", pull_lines(repo, token, since, until)),
        (f"Коммиты в {branch}", commit_lines(repo, token, branch, since, until)),
        ("Задачи", issue_lines(repo, token, since, until)),
    ]
    body = [section(header, lines) for header, lines in sections if lines]
    if not body:
        print(f"{repo}: за ночь событий нет", file=sys.stderr)
        return

    text = "\n\n".join([f"🌙 <b>За ночь в {html.escape(repo)}</b>", *body])
    if len(text) > TELEGRAM_TEXT_LIMIT:
        # Обрезаем по строкам, чтобы не порвать HTML-тег посередине.
        kept = []
        for line in text.split("\n"):
            if len("\n".join([*kept, line])) > TELEGRAM_TEXT_LIMIT - len("\n…"):
                break
            kept.append(line)
        text = "\n".join([*kept, "…"])
    send_telegram(env["BOT_TOKEN"], env["CHAT_ID"], text)


if __name__ == "__main__":
    main()
