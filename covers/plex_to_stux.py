#!/usr/bin/env python3
"""
Stux on Wax — Plex library export
=================================
Reads every album in your Plex music library and writes it out for the catalogue page:

  plex_library.js        the album list (loaded by index.html — works from disk and GitHub Pages)
  covers/plex/<n>/<key>.jpg  a 150px thumbnail per album, in numbered sub-folders of under 100
                             files each (GitHub's web uploader refuses more than 100 files at once)

Setup:  pip install requests
        plex_config.json must exist (copy plex_config.example.json) with plex_url and plex_token

Usage:  python plex_to_stux.py             # export the album list (no artwork — 9,600 thumbnails
                                           #   is ~120 MB, too much for the GitHub site)
        python plex_to_stux.py --art       # also download thumbnails into covers/plex/ (git-ignored)
"""
import argparse, json, sys, time
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "plex_config.json"
OUT_JS = HERE / "plex_library.js"
ART_DIR = HERE / "covers" / "plex"
PAGE = 200


def cfg():
    if not CONFIG.exists():
        sys.exit("plex_config.json not found — copy plex_config.example.json and fill it in")
    c = json.loads(CONFIG.read_text())
    return c["plex_url"].rstrip("/"), c["plex_token"]


def connect(base, token):
    """Return a base URL that answers. Tries the configured URL, then the other scheme
    (Plex set to 'Secure connections: Required' closes plain http without a reply)."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    candidates = [base]
    if base.startswith("http://"):
        candidates.append("https://" + base[7:])
    elif base.startswith("https://"):
        candidates.append("http://" + base[8:])
    for url in candidates:
        try:
            r = SESSION.get(f"{url}/identity", params={"X-Plex-Token": token}, timeout=10,
                            verify=not url.startswith("https://"))
            if r.status_code == 401:
                sys.exit("Plex rejected the token (401) — check plex_token in plex_config.json")
            r.raise_for_status()
            if url != base:
                print(f"Note: {base} didn't answer, but {url} does — update plex_url in plex_config.json")
            if url.startswith("https://"):
                SESSION.verify = False   # Plex's certificate is for *.plex.direct, not a LAN IP
            return url
        except requests.RequestException as e:
            print(f"  {url}: {e.__class__.__name__}")
    sys.exit("Couldn't reach Plex on http or https at that address.\n"
             "  - Is the server on and still at that IP?  (Plex app → Settings → Remote Access shows it)\n"
             "  - Settings → Network → 'Secure connections' set to Preferred rather than Required also fixes this")


SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/xml", "Connection": "close",
                        "X-Plex-Client-Identifier": "stux-on-wax", "X-Plex-Product": "Stux on Wax"})


def fetch(url, params, tries=5):
    """GET with retries — Plex sometimes drops a connection when it's busy transcoding."""
    for attempt in range(1, tries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=60, verify=SESSION.verify)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.ConnectionError(f"HTTP {r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == tries:
                raise
            wait = 2 * attempt
            print(f"    connection problem ({e.__class__.__name__}) — retrying in {wait}s")
            time.sleep(wait)


def get(url, token, **params):
    params["X-Plex-Token"] = token
    r = fetch(url, params)
    r.raise_for_status()
    return ET.fromstring(r.content)


def bucket(key, n):
    return int(key) % n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", action="store_true", help="also download thumbnails (local use only)")
    ap.add_argument("--force-art", action="store_true")
    a = ap.parse_args()
    base, token = cfg()
    base = connect(base, token)

    ident = get(f"{base}/identity", token)
    machine = ident.get("machineIdentifier")
    print(f"Connected to Plex server {ident.get('version','?')}  (id {machine[:8]}…)")

    sections = get(f"{base}/library/sections", token)
    music = [s for s in sections.findall("Directory") if s.get("type") == "artist"]
    if not music:
        sys.exit("No music library found on this server")
    print("Music libraries: " + ", ".join(f"{s.get('title')} (#{s.get('key')})" for s in music))

    albums = []
    for sec in music:
        start = 0
        while True:
            page = get(f"{base}/library/sections/{sec.get('key')}/all", token,
                       type=9, **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": PAGE})
            items = page.findall("Directory")
            for d in items:
                albums.append({
                    "key": d.get("ratingKey"),
                    "artist": d.get("parentTitle") or "",
                    "title": d.get("title") or "",
                    "year": int(d.get("year")) if d.get("year") else None,
                    "tracks": int(d.get("leafCount") or 0),
                    "genres": [g.get("tag") for g in d.findall("Genre")][:3],
                    "added": time.strftime("%Y-%m-%d", time.localtime(int(d.get("addedAt") or 0))),
                    "thumb": d.get("thumb"),
                    "lib": sec.get("title"),
                })
            start += PAGE
            total = int(page.get("totalSize") or 0)
            print(f"  {sec.get('title')}: {min(start,total)}/{total}")
            if start >= total or not items:
                break

    albums.sort(key=lambda x: (x["artist"].lower(), x["title"].lower()))
    print(f"{len(albums)} albums exported")

    # pick a bucket count so no covers/plex/<n>/ folder holds more than ~90 files
    n = max(1, -(-len(albums) // 80))
    while albums and max(sum(1 for x in albums if bucket(x["key"], n) == b) for b in range(n)) > 90:
        n += 1
    art_path = lambda x: ART_DIR / str(bucket(x["key"], n)) / f"{x['key']}.jpg"

    # move any thumbnails saved by an older run (flat covers/plex/<key>.jpg) into their buckets
    for old in ART_DIR.glob("*.jpg"):
        dest = ART_DIR / str(bucket(old.stem, n)) / old.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        old.replace(dest)

    if a.art or a.force_art:
        todo = [x for x in albums if x["thumb"] and (a.force_art or not art_path(x).exists())]
        print(f"Thumbnails: {len(albums)-len(todo)} already saved, {len(todo)} to fetch (into {n} sub-folders)")
        failed = 0
        for i, x in enumerate(todo, 1):
            try:
                r = fetch(f"{base}/photo/:/transcode",
                          {"width": 150, "height": 150, "minSize": 1, "upscale": 1,
                           "url": x["thumb"], "X-Plex-Token": token})
                if r.ok and r.headers.get("content-type", "").startswith("image"):
                    p = art_path(x); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(r.content)
                else:
                    failed += 1; print(f"  x {x['artist']} – {x['title']} ({r.status_code})")
            except Exception as e:
                failed += 1; print(f"  x {x['artist']} – {x['title']}: {e}")
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}…")
            time.sleep(0.05)   # give the Plex transcoder a breather
        if failed:
            print(f"{failed} thumbnails failed — just run the script again to retry those")

    for x in albums:
        x["art"] = (a.art or a.force_art) and art_path(x).exists()
        del x["thumb"]
    data = {"machine": machine, "fetched": time.strftime("%d %b %Y"), "buckets": n, "albums": albums}
    OUT_JS.write_text("window.PLEX = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                      encoding="utf-8")
    print(f"Wrote {OUT_JS.name} — open index.html to see the combined catalogue")


if __name__ == "__main__":
    main()
