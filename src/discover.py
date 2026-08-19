from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

BASE_URL = "https://simulatorgolftour.com"
ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with (ROOT / "config.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def browser_headers(tour_id: int, *, ajax: bool = False) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{BASE_URL}/tour/{tour_id}",
    }
    if ajax:
        headers.update(
            {
                "Accept": "text/html, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
    else:
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        )
    return headers


def response_preview(body: bytes, limit: int = 1200) -> str:
    return body[:limit].decode("utf-8", errors="replace").replace("\n", " ")


def open_with_diagnostics(opener, request: urllib.request.Request, label: str) -> bytes:
    print(f"REQUEST {label}: {request.full_url}")
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read()
            print(
                f"RESPONSE {label}: HTTP {response.status} | "
                f"content-type={response.headers.get('Content-Type')} | bytes={len(body)}"
            )
            return body
    except urllib.error.HTTPError as exc:
        body = exc.read()
        print(f"ERROR {label}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        print(f"ERROR content-type: {exc.headers.get('Content-Type')}", file=sys.stderr)
        print(f"ERROR server: {exc.headers.get('Server')}", file=sys.stderr)
        print(f"ERROR response preview: {response_preview(body)}", file=sys.stderr)
        raise
    except urllib.error.URLError as exc:
        print(f"ERROR {label}: URL error: {exc.reason}", file=sys.stderr)
        raise


def fetch_events_html(tour_id: int) -> str:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    # First establish the same public page context a browser would have before
    # requesting the dynamically loaded events fragment.
    tour_request = urllib.request.Request(
        f"{BASE_URL}/tour/{tour_id}",
        headers=browser_headers(tour_id),
    )
    open_with_diagnostics(opener, tour_request, "tour-page")
    print(f"COOKIES after tour page: {len(cookie_jar)}")

    cache_buster = int(time.time() * 1000)
    events_url = f"{BASE_URL}/sgt-api/tour/{tour_id}/events?_={cache_buster}"
    events_request = urllib.request.Request(
        events_url,
        headers=browser_headers(tour_id, ajax=True),
    )
    body = open_with_diagnostics(opener, events_request, "events")
    return body.decode("utf-8", errors="replace")


def text(node) -> str | None:
    return node.get_text(" ", strip=True) if node else None


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%b %d, %Y").date().isoformat()
    except ValueError:
        return value


def winner_from_card(card, label: str) -> str | None:
    wanted = label.upper()
    for node in card.find_all("div"):
        if text(node) and text(node).upper() == wanted:
            parent = node.parent
            link = parent.find("a", href=re.compile(r"^/profile/")) if parent else None
            return text(link)
    return None


def parse_event_card(card, status: str) -> dict | None:
    tournament_link = card.find("a", href=re.compile(r"^/tournament/\d+$"))
    if not tournament_link:
        return None

    match = re.search(r"/tournament/(\d+)", tournament_link.get("href", ""))
    if not match:
        return None

    info = card.find("div", class_=lambda value: value and "flex-fill" in value)
    direct = info.find_all("div", recursive=False) if info else []

    tour_name = text(direct[0]) if len(direct) > 0 else None
    course = text(direct[1]) if len(direct) > 1 else None
    display_date = text(direct[2]) if len(direct) > 2 else None

    event = {
        "id": int(match.group(1)),
        "status": status,
        "tourName": tour_name,
        "course": course,
        "date": parse_date(display_date),
        "displayDate": display_date,
        "url": f"{BASE_URL}{tournament_link.get('href')}",
    }

    if status == "completed":
        event["grossWinner"] = winner_from_card(card, "GROSS WINNER")
        event["netWinner"] = winner_from_card(card, "NET WINNER")

    return event


def parse_events(html: str, tour_id: int, configured_name: str | None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "tourId": tour_id,
        "tourName": configured_name,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "active": [],
        "completed": [],
    }

    heading_map = {
        "ACTIVE EVENTS": ("active", "active"),
        "PAST EVENTS": ("completed", "completed"),
    }

    for heading in soup.find_all("h2"):
        heading_text = text(heading)
        if not heading_text:
            continue
        key = heading_text.upper()
        if key not in heading_map:
            continue

        output_key, status = heading_map[key]
        container = heading.find_next_sibling("div")
        if not container:
            continue

        for card in container.select("div.event-card"):
            event = parse_event_card(card, status)
            if event:
                result[output_key].append(event)

    if not result["active"] and not result["completed"]:
        print("PARSE ERROR response preview:", html[:1600].replace("\n", " "), file=sys.stderr)
        raise RuntimeError(
            "SGT response was fetched, but no ACTIVE or PAST event cards were found."
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover SGT tour events.")
    parser.add_argument("--write", type=Path, help="Optional path for normalized JSON output.")
    args = parser.parse_args()

    config = load_config()
    tour_id = int(config["tourId"])
    tour_name = config.get("tourName")

    print(f"Starting read-only SGT discovery for Tour {tour_id}")
    html = fetch_events_html(tour_id)
    discovered = parse_events(html, tour_id, tour_name)

    print(f"Tour {tour_id}: {len(discovered['active'])} active, {len(discovered['completed'])} completed")
    if discovered["active"]:
        newest_active = discovered["active"][0]
        print(f"Active: {newest_active['id']} | {newest_active['course']} | {newest_active['date']}")
    if discovered["completed"]:
        latest = discovered["completed"][0]
        print(
            "Latest completed: "
            f"{latest['id']} | {latest['course']} | {latest['date']} | "
            f"net={latest.get('netWinner')} | gross={latest.get('grossWinner')}"
        )

    print(json.dumps(discovered, indent=2))

    if args.write:
        output = args.write if args.write.is_absolute() else ROOT / args.write
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(discovered, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
