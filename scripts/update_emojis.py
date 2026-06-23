#!/usr/bin/env python3
"""Update a GitHub gist with the current list of GitHub emojis."""

import json
import os
import sys
from datetime import date

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GIST_ID = os.environ["GIST_ID"]

EMOJIS_MD_FILE = "emojis.md"
STATE_FILE = "emojis-state.json"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

CATEGORIES_FILE = os.path.join(os.path.dirname(__file__), "..", "emoji_categories.json")


def get_category(name: str, categories: dict) -> str:
    return categories.get("mappings", {}).get(name, categories.get("default_category", "Uncategorized"))


def fetch_emojis() -> dict[str, str]:
    resp = requests.get("https://api.github.com/emojis", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_gist() -> dict:
    resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_state(gist_data: dict) -> dict:
    files = gist_data.get("files", {})
    if STATE_FILE in files:
        raw = files[STATE_FILE].get("content", "")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {"emojis": [], "changelog": []}


def build_markdown(emojis: dict[str, str], categories_config: dict, changelog: list) -> str:
    today = date.today().isoformat()
    total = len(emojis)

    grouped: dict[str, list[str]] = {}
    for name in sorted(emojis.keys()):
        cat = get_category(name, categories_config)
        grouped.setdefault(cat, []).append(name)

    lines = [
        "# GitHub Emojis",
        "",
        f"> Last updated: {today} | Total: {total} emojis",
        "",
    ]

    for category, names in sorted(grouped.items()):
        lines += [
            f"## {category}",
            "",
            "| Preview | Name |",
            "|---------|------|",
        ]
        for name in names:
            lines.append(f"| :{name}: | `{name}` |")
        lines.append("")

    lines += [
        "---",
        "",
        "## Changelog",
        "",
    ]

    if not changelog:
        lines.append("_No changes recorded yet._")
        lines.append("")
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


def update_gist(md_content: str, state: dict) -> str:
    payload = {
        "files": {
            EMOJIS_MD_FILE: {"content": md_content},
            STATE_FILE: {"content": json.dumps(state, indent=2)},
        }
    }
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

    gist_data = fetch_gist()
    state = parse_state(gist_data)

    previous_names = set(state.get("emojis", []))
    changelog = state.get("changelog", [])

    is_first_run = not previous_names

    added = sorted(current_names - previous_names)
    removed = sorted(previous_names - current_names)

    if not is_first_run and not added and not removed:
        print("No emoji changes detected. Skipping update.")
        sys.exit(0)

    if is_first_run:
        print(f"First run — initializing gist with {len(current_names)} emojis.")
    else:
        print(f"Changes detected: +{len(added)} added, -{len(removed)} removed.")
        if added:
            preview = ", ".join(added[:10]) + ("…" if len(added) > 10 else "")
            print(f"  Added: {preview}")
        if removed:
            preview = ", ".join(removed[:10]) + ("…" if len(removed) > 10 else "")
            print(f"  Removed: {preview}")

        entry: dict = {"date": date.today().isoformat()}
        if added:
            entry["added"] = added
        if removed:
            entry["removed"] = removed
        changelog.append(entry)

    new_state = {
        "emojis": sorted(current_names),
        "changelog": changelog,
        "last_updated": date.today().isoformat(),
    }

    md_content = build_markdown(current_emojis, categories_config, changelog)
    url = update_gist(md_content, new_state)
    print(f"Gist updated: {url}")


if __name__ == "__main__":
    main()
