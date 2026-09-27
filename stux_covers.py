#!/usr/bin/env python3
"""
Stux on Wax — cover art fetcher
================================
Does two jobs, both driven by the Discogs collection data embedded in index.html:

  1. PAGE COVERS   Downloads every record's Discogs thumbnail into covers/<release_id>.jpg
                   so the catalogue page shows art without hotlinking Discogs (which blocks it).
                   index.html tries covers/<id>.jpg first and falls back to the Discogs URL.

  2. MP3 ART       For every album folder in digitized_vinyl/, finds the matching Discogs
                   release, downloads the full-size primary image via the Discogs API,
                   saves it as cover.jpg in the album folder and embeds it (APIC) in each MP3.
                   Plex and the index generator both pick up cover.jpg.

Setup
-----
  pip install requests mutagen
  Copy discogs_config.example.json to discogs_config.json and paste in a personal access
  token from https://www.discogs.com/settings/developers   (needed for full-size images only)

Usage
-----
  python stux_covers.py            # page thumbnails only (default — no token, no mutagen needed)
  python stux_covers.py --mp3      # also fetch full-size art and embed it in the digitised MP3s
  python stux_covers.py --mp3 --force   # re-embed even where art already exists

If an album folder can't be matched automatically, add it to cover_map.json:
  { "Artist/Album folder name": 1144126 }     (value = Discogs release id)
"""
import argparse, json, os, re, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
COVERS = HERE / "covers"
LIBRARY = HERE / "digitized_vinyl"
MAP_FILE = HERE / "cover_map.json"
CONFIG = HERE / "discogs_config.json"
UA = "StuxOnWax/1.0 +https://github.com/stuartmcneil"
API = "https://api.discogs.com"


# ---------- helpers ----------
def load_collection():
    """Pull the embedded collection JSON out of index.html."""
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


def norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)          # drop (remix) [reissue] etc
    s = re.sub(r"^(the|a|an)\s+", "", s.strip())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get(url, tok="", stream=False):
    """GET with Discogs' rate limit respected (60/min with a token, 25/min without)."""
    h = {"User-Agent": UA}
    if tok:
        h["Authorization"] = f"Discogs token={tok}"
    for attempt in range(4):
        r = requests.get(url, headers=h, timeout=30, stream=stream)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 10))
            print(f"    rate limited — waiting {wait}s")
            time.sleep(wait)
            continue
        return r
    return r


# ---------- job 1: page thumbnails ----------
def page_covers(records):
    COVERS.mkdir(exist_ok=True)
    todo = [r for r in records if r.get("cover") and not (COVERS / f"{r['id']}.jpg").exists()]
    print(f"Page covers: {len(records) - len(todo)} already saved, {len(todo)} to fetch")
    ok = fail = 0
    for i, r in enumerate(todo, 1):
        try:
            resp = get(r["cover"])
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                (COVERS / f"{r['id']}.jpg").write_bytes(resp.content)
                ok += 1
            else:
                fail += 1
                print(f"  x {r['artist']} – {r['title']} ({resp.status_code})")
        except Exception as e:
            fail += 1
            print(f"  x {r['artist']} – {r['title']}: {e}")
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}…")
        time.sleep(0.4)   # be polite to the image CDN
    print(f"Page covers done: {ok} saved, {fail} failed\n")


# ---------- job 2: MP3 art ----------
def match_release(artist_dir, album_dir, records, manual):
    key = f"{artist_dir}/{album_dir}"
    if key in manual:
        rid = int(manual[key])
        return next((r for r in records if r["id"] == rid), None)
    a, t = norm(artist_dir), norm(album_dir)
    cands = [r for r in records if norm(r["artist"]) == a and norm(r["title"]) == t]
    if not cands:   # looser: artist contained / title prefix
        cands = [r for r in records
                 if (a in norm(r["artist"]) or norm(r["artist"]) in a)
                 and (norm(r["title"]).startswith(t) or t.startswith(norm(r["title"])))]
    if not cands:
        return None
    # prefer an LP / Album over a single or compilation, then the earliest pressing
    cands.sort(key=lambda r: (("Album" not in r["format"]), r.get("year") or 9999))
    return cands[0]


def full_image_url(release_id, tok):
    r = get(f"{API}/releases/{release_id}", tok)
    if r.status_code != 200:
        return None
    imgs = r.json().get("images") or []
    primary = next((i for i in imgs if i.get("type") == "primary"), imgs[0] if imgs else None)
    return primary.get("uri") if primary else None


def embed(mp3_path, jpeg_bytes, force):
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()
    if tags.getall("APIC") and not force:
        return False
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpeg_bytes))
    tags.save(mp3_path, v2_version=3)
    return True


def mp3_art(records, force):
    try:
        import mutagen  # noqa
    except ImportError:
        sys.exit("pip install mutagen")
    tok = token()
    if not tok:
        print("No Discogs token found (discogs_config.json or DISCOGS_TOKEN) — "
              "full-size images need one, so falling back to the 150px thumbnails.\n")
    manual = json.loads(MAP_FILE.read_text()) if MAP_FILE.exists() else {}
    unmatched = []
    for artist_dir in sorted(p for p in LIBRARY.iterdir() if p.is_dir()):
        for album_dir in sorted(p for p in artist_dir.iterdir() if p.is_dir()):
            mp3s = sorted(album_dir.glob("*.mp3"))
            if not mp3s:
                continue
            label = f"{artist_dir.name} – {album_dir.name}"
            cover = album_dir / "cover.jpg"
            if cover.exists() and not force:
                data = cover.read_bytes()
            else:
                rel = match_release(artist_dir.name, album_dir.name, records, manual)
                if not rel:
                    unmatched.append(f"{artist_dir.name}/{album_dir.name}")
                    print(f"  ? {label}: no Discogs match — add to cover_map.json")
                    continue
                url = full_image_url(rel["id"], tok) if tok else rel.get("cover")
                time.sleep(1.1)
                if not url:
                    print(f"  x {label}: release {rel['id']} has no image")
                    continue
                resp = get(url, tok)
                if resp.status_code != 200:
                    print(f"  x {label}: image download failed ({resp.status_code})")
                    continue
                data = resp.content
                cover.write_bytes(data)
                print(f"  ✓ {label}  ←  Discogs {rel['id']} ({len(data)//1024} KB)")
            n = sum(embed(str(p), data, force) for p in mp3s)
            if n:
                print(f"    embedded in {n}/{len(mp3s)} tracks")
    if unmatched:
        print("\nUnmatched folders — map them in cover_map.json as \"Artist/Album\": <release_id>:")
        for u in unmatched:
            print("  ", u)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", action="store_true", help="page thumbnails (the default)")
    ap.add_argument("--mp3", action="store_true", help="also embed full-size art in the digitised MP3s")
    ap.add_argument("--force", action="store_true", help="re-download / re-embed existing art")
    a = ap.parse_args()
    records = load_collection()
    print(f"{len(records)} records in the collection\n")
    if not a.mp3 or a.page:
        page_covers(records)
    if a.mp3:
        mp3_art(records, a.force)
