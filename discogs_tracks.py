#!/usr/bin/env python3
"""
Stux on Wax — Discogs track lists & release details
===================================================
Fetches, for every record in the collection embedded in index.html, its Discogs release:
track list (side/position, title, duration, track artists on compilations), country, release
date, format details and pressing notes. Writes discogs_tracks.js for the page.

Setup:  pip install requests
        Optional but recommended: discogs_config.json with a personal access token
        (copy discogs_config.example.json; token from https://www.discogs.com/settings/developers).
        With a token Discogs allows 60 requests/min; without, 25/min.

Usage:  python discogs_tracks.py            # fetch anything not yet fetched (resumable)
        python discogs_tracks.py --refresh  # re-fetch everything
"""
import argparse, json, os, re, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
OUT_JS = HERE / "discogs_tracks.js"
CACHE = HERE / "discogs_tracks_cache.json"      # git-ignored; lets a stopped run resume
CONFIG = HERE / "discogs_config.json"
UA = "StuxOnWax/1.0 +https://github.com/stuartmcneil/Stux-on-Wax"
API = "https://api.discogs.com"


def load_collection():
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        sys.exit("Couldn't find the collection data in index.html")
    return json.loads(m.group(1).replace("<\\/", "</"))


def token():
    if os.environ.get("DISCOGS_TOKEN"):
        return os.environ["DISCOGS_TOKEN"]
    if CONFIG.exists():
        return json.loads(CONFIG.read_text()).get("token", "")
    return ""


def get(url, tok):
    h = {"User-Agent": UA}
    if tok:
        h["Authorization"] = f"Discogs token={tok}"
    for attempt in range(1, 6):
        try:
            r = requests.get(url, headers=h, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"    connection problem ({e.__class__.__name__}) — retrying in {2*attempt}s")
            time.sleep(2 * attempt); continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 30))
            print(f"    rate limited — waiting {wait}s")
            time.sleep(wait); continue
        return r
    return r


def secs(d):
    """'4:32' -> 272"""
    m = re.match(r"^\s*(\d+):(\d\d)\s*$", d or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    tok = token()
    delay = 1.05 if tok else 2.5
    print("Discogs token:", "yes (60 req/min)" if tok else "none — 25 req/min; add discogs_config.json to go faster")

    records = load_collection()
    cache = {} if a.refresh or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    todo = [r for r in records if str(r["id"]) not in cache]
    print(f"{len(records)} records: {len(records)-len(todo)} cached, {len(todo)} to fetch "
          f"(~{len(todo)*delay/60:.0f} min)")

    failed = 0
    for i, r in enumerate(todo, 1):
        resp = get(f"{API}/releases/{r['id']}", tok)
        if resp.status_code != 200:
            failed += 1
            print(f"  x {r['artist']} – {r['title']} ({resp.status_code})")
            time.sleep(delay); continue
        d = resp.json()
        tracks = []
        for t in d.get("tracklist", []):
            if t.get("type_") == "heading":
                continue
            row = [t.get("position", ""), t.get("title", ""), secs(t.get("duration"))]
            arts = t.get("artists")
            if arts:
                row.append(", ".join(x["name"] for x in arts))
            tracks.append(row)
        fmt = "; ".join(
            " · ".join(filter(None, [f.get("name"), ", ".join(f.get("descriptions", [])), f.get("text")]))
            for f in d.get("formats", []))
        cache[str(r["id"])] = {
            "t": tracks,
            "country": d.get("country", ""),
            "released": d.get("released", ""),
            "fmt": fmt,
            "notes": (d.get("notes") or "").strip()[:600],
            "master": d.get("master_id"),
            "have": d.get("community", {}).get("have"),
            "want": d.get("community", {}).get("want"),
        }
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}…")
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(delay)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if failed:
        print(f"{failed} releases failed — run again to retry those")
    n = sum(len(v["t"]) for v in cache.values())
    OUT_JS.write_text("window.DISCOGS_TRACKS = " + json.dumps(cache, ensure_ascii=False, separators=(",", ":")) + ";\n",
                      encoding="utf-8")
    print(f"Wrote {OUT_JS.name}: {len(cache)} releases, {n} tracks ({OUT_JS.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
