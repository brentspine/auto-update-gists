#!/usr/bin/env python3
"""Update a GitHub gist with the current list of GitHub emojis."""

import json
import os
from datetime import date

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GIST_ID = os.environ["GIST_ID"]

EMOJIS_MD_FILE = "emojis.md"
EMOJIS_PER_ROW = 3

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

ROOT = os.path.join(os.path.dirname(__file__), "..")
CATEGORIES_FILE = os.path.join(ROOT, "emoji_categories.json")
STATE_FILE = os.path.join(ROOT, "emoji_state.json")


def get_category(name: str, categories: dict) -> str:
    return categories.get("mappings", {}).get(name, categories.get("default_category", "Uncategorized"))


def fetch_emojis() -> dict[str, str]:
    resp = requests.get("https://api.github.com/emojis", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {"emojis": [], "changelog": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def build_emoji_table(names: list[str]) -> list[str]:
    lines = ["|" + "|".join([" "] * EMOJIS_PER_ROW) + "|",
             "|" + "|".join(["---"] * EMOJIS_PER_ROW) + "|"]
    for i in range(0, len(names), EMOJIS_PER_ROW):
        chunk = names[i:i + EMOJIS_PER_ROW]
        cells = [f" :{name}: `{name}` " for name in chunk]
        cells += [" "] * (EMOJIS_PER_ROW - len(cells))
        lines.append("|" + "|".join(cells) + "|")
    return lines


def _category_anchor(name: str) -> str:
    return "#" + name.lower().replace(" ", "-")


def build_markdown(emojis: dict[str, str], categories_config: dict, changelog: list, last_updated: str, last_checked: str) -> str:
    total = len(emojis)

    grouped: dict[str, list[str]] = {}
    for name in sorted(emojis.keys()):
        cat = get_category(name, categories_config)
        grouped.setdefault(cat, []).append(name)

    order: list[str] = categories_config.get("category_order", [])
    ordered_keys = [c for c in order if c in grouped]
    ordered_keys += sorted(c for c in grouped if c not in order)

    lines = [
        "# GitHub Emojis",
        "",
        f"> Last updated: {last_updated} | Last checked: {last_checked} | Total: {total} emojis",
        "",
        "To recategorize an emoji, [create a PR](https://github.com/brentspine/auto-update-gists) on the repository.",
        "",
    ]

    lines += ["## Categories", ""]
    for category in ordered_keys:
        lines.append(f"- [{category}]({_category_anchor(category)})")
    lines.append("")

    for category in ordered_keys:
        lines += [f"## {category}", ""]
        lines += build_emoji_table(grouped[category])
        lines.append("")

    lines += ["---", "", "## Changelog", ""]

    if not changelog:
        lines += ["_No changes recorded yet._", ""]
    else:
        for entry in reversed(changelog):
            lines.append(f"### {entry['date']}")
            added = entry.get("added", [])
            removed = entry.get("removed", [])
            if added:
                lines.append(f"- **Added** ({len(added)}): " + ", ".join(f"`{e}`" for e in added))
            if removed:
                lines.append(f"- **Removed** ({len(removed)}): " + ", ".join(f"`{e}`" for e in removed))
            lines.append("")

    return "\n".join(lines)


def update_gist(md_content: str) -> str:
    payload = {"files": {EMOJIS_MD_FILE: {"content": md_content}}}
    resp = requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]


def main() -> None:
    with open(CATEGORIES_FILE) as f:
        categories_config = json.load(f)

    current_emojis = fetch_emojis()
    current_names = set(current_emojis.keys())

    state = load_state()
    previous_names = set(state.get("emojis", []))
    changelog = state.get("changelog", [])

    is_first_run = not previous_names
    added = sorted(current_names - previous_names)
    removed = sorted(previous_names - current_names)

    today = date.today().isoformat()
    last_checked = today

    if not is_first_run and not added and not removed:
        print("No emoji changes detected. Updating gist with latest check date.")
        last_updated = state.get("last_updated", today)
    elif is_first_run:
        print(f"First run — initializing gist with {len(current_names)} emojis.")
        last_updated = today
    else:
        print(f"Changes detected: +{len(added)} added, -{len(removed)} removed.")
        if added:
            print(f"  Added: {', '.join(added[:10])}{'…' if len(added) > 10 else ''}")
        if removed:
            print(f"  Removed: {', '.join(removed[:10])}{'…' if len(removed) > 10 else ''}")

        entry: dict = {"date": today}
        if added:
            entry["added"] = added
        if removed:
            entry["removed"] = removed
        changelog.append(entry)
        last_updated = today

    new_state = {
        "emojis": sorted(current_names),
        "changelog": changelog,
        "last_updated": last_updated,
        "last_checked": last_checked,
    }

    md_content = build_markdown(current_emojis, categories_config, changelog, last_updated, last_checked)
    url = update_gist(md_content)
    save_state(new_state)
    print(f"Gist updated: {url}")


if __name__ == "__main__":
    main()
