from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE_URL = "https://simulatorgolftour.com"
ROOT = Path(__file__).resolve().parents[1]
TOURNAMENT_ID = 67350
PLAYER_ID = 25820  # CDickerson, observed in the browser HAR for tournament 67350.


def build_opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (compatible; SGTRecapEngineLab/0.2)"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def fetch(opener: urllib.request.OpenerDirector, path: str, referer: str) -> tuple[bytes, dict]:
    url = f"{BASE_URL}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html, */*; q=0.01",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read()
            meta = {
                "url": url,
                "status": getattr(response, "status", None),
                "contentType": response.headers.get("Content-Type"),
                "server": response.headers.get("Server"),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            return body, meta
    except urllib.error.HTTPError as exc:
        body = exc.read()
        preview = body[:500].decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} fetching {url}", file=sys.stderr)
        print(f"Content-Type: {exc.headers.get('Content-Type')}", file=sys.stderr)
        print(f"Server: {exc.headers.get('Server')}", file=sys.stderr)
        print(f"Response preview: {preview!r}", file=sys.stderr)
        raise


def main() -> None:
    opener = build_opener()
    tournament_url = f"{BASE_URL}/tournament/{TOURNAMENT_ID}"

    # Prime whatever cookies/session state SGT wants from a normal public page visit.
    with opener.open(tournament_url, timeout=30) as response:
        response.read()
        print(f"Tournament page: HTTP {getattr(response, 'status', None)}")

    targets = {
        "gross_leaderboard": f"/sgt-api/leaderboard/{TOURNAMENT_ID}",
        "net_leaderboard": f"/sgt-api/leaderboard/{TOURNAMENT_ID}/net",
        "scorecard": f"/sgt-api/scorecard/{TOURNAMENT_ID}/{PLAYER_ID}/indv",
        "stats": f"/sgt-api/scorecard/{TOURNAMENT_ID}/{PLAYER_ID}/indv/stats",
        "shots": f"/sgt-api/scorecard/{TOURNAMENT_ID}/{PLAYER_ID}/indv/shots",
    }

    output_dir = ROOT / "data" / "raw" / str(TOURNAMENT_ID)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "tournamentId": TOURNAMENT_ID,
        "playerId": PLAYER_ID,
        "playerName": "CDickerson",
        "requests": {},
    }

    for name, path in targets.items():
        referer = tournament_url if "leaderboard" in name else f"{BASE_URL}/scorecard/{TOURNAMENT_ID}/{PLAYER_ID}"
        body, meta = fetch(opener, path, referer)
        if not body.strip():
            raise RuntimeError(f"{name} returned an empty response")
        file_path = output_dir / f"{name}.html"
        file_path.write_bytes(body)
        meta["file"] = str(file_path.relative_to(ROOT))
        manifest["requests"][name] = meta
        print(f"{name}: HTTP {meta['status']} | {meta['bytes']} bytes")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
