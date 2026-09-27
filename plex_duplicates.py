#!/usr/bin/env python3
"""
Stux on Wax — Plex duplicate finder
===================================
Reads plex_tracks_cache.json (written by `plex_to_stux.py --tracks`) and finds duplicate
music files. Nothing is deleted unless you ask for it.

Two kinds of duplicate are reported:

  ALBUM COPIES   whole folders that hold the same album (same artist + title, and most track
                 titles in common) — e.g. a CD rip and a download of the same record.
  TRACK COPIES   within one Plex album, tracks with the same title (ignoring case, punctuation
                 and bracketed suffixes like "(Remastered)") and a similar length.

For every group the best copy is marked KEEP (highest bitrate, then largest file, lossless
first) and the others DELETE.

Usage
-----
  python plex_duplicates.py                 # write plex_duplicates.csv + a summary
  python plex_duplicates.py --move          # after reviewing the CSV: move every DELETE file
                                            #   into <music root>\\_duplicates\\ (same sub-path),
                                            #   so nothing is lost until you empty that folder
  python plex_duplicates.py --move --dry-run
  python plex_duplicates.py --move --exact   # only whole-album copies whose track lists match
                                             #   100% and carry no NOTE — the safe first pass

  Plex on a NAS?  Its paths (e.g. /volume1/PLEX/Music) aren't valid on this PC, so tell the
  script how this PC reaches them:
    python plex_duplicates.py --move --map "/volume1/PLEX=\\\\NAS\\PLEX"      (UNC share)
    python plex_duplicates.py --move --map "/volume1/PLEX=P:"                (mapped drive)
  The mapping is remembered in plex_config.json after the first use.

After moving: Plex → your music library → ⋯ → Scan Library Files, then ⋯ → Empty Trash.
"""
import argparse, csv, json, os, re, shutil, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "plex_tracks_cache.json"
LIB = HERE / "plex_library.js"
OUT = HERE / "plex_duplicates.csv"
LOSSLESS = {"flac", "alac", "wav", "aiff", "ape", "pcm"}


def norm(s):
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)                 # (remastered) [live] etc
    s = re.sub(r"\b(feat|ft|featuring)\b.*$", " ", s)
    s = re.sub(r"^\s*\d{1,2}\s*[-._ ]\s*", "", s)         # leading "01 - "
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def r9prefix(p):
    """Best guess at the share-level prefix of a NAS path: /volume1/PLEX/Music/x -> /volume1/PLEX"""
    parts = p.replace("\\", "/").split("/")
    return "/".join(parts[:3]) if p.startswith("/") and len(parts) > 3 else str(Path(p).parent)


def quality(f):
    """Sort key: better copy first."""
    _, path, size, br, codec = f
    return ((codec or "").lower() in LOSSLESS, br or 0, size or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--move", action="store_true", help="move DELETE files into _duplicates/")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--map", help='translate Plex paths: "<plex prefix>=<path on this PC>"')
    ap.add_argument("--exact", action="store_true", help="move only 100%%-match album copies without a NOTE")
    ap.add_argument("--min-match", type=int, default=0, help="move only album copies matching at least this %%")
    a = ap.parse_args()
    cfgp = HERE / "plex_config.json"
    cfg = json.loads(cfgp.read_text()) if cfgp.exists() else {}
    if a.map:
        src_prefix, _, dst_prefix = a.map.partition("=")
        cfg["path_map"] = [src_prefix.strip(), dst_prefix.strip()]
        cfgp.write_text(json.dumps(cfg, indent=2))
    pmap = cfg.get("path_map")

    def local(p):
        """Plex's path -> this PC's path."""
        q = p.replace("\\", "/")
        if pmap and q.lower().startswith(pmap[0].replace("\\", "/").lower()):
            q = pmap[1] + q[len(pmap[0]):]
        return q.replace("/", "\\") if os.name == "nt" else q

    if not CACHE.exists():
        sys.exit("plex_tracks_cache.json not found — run: python plex_to_stux.py --tracks")
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    if not any("files" in v for v in cache.values()):
        sys.exit("The cache has no file paths yet — run: python plex_to_stux.py --tracks")
    lib = json.loads(LIB.read_text(encoding="utf-8").split("=", 1)[1].rstrip(";\n"))
    albums = {x["key"]: x for x in lib["albums"]}

    rows = []          # CSV rows
    groups = 0
    flagged = set()    # file paths already marked DELETE (so a file is only listed once)

    # ---------- 1. album copies: same artist + (title or folder), different folders ----------
    by_album = defaultdict(list)
    for key, v in cache.items():
        al = albums.get(key)
        if not al or not v.get("files"):
            continue
        title = al["title"].strip() or al.get("folder") or v.get("f") or ""
        if not title:
            continue
        folders = defaultdict(list)
        for f in v["files"]:
            if f[1]:
                folders[str(Path(f[1].replace("\\", "/")).parent)].append(f)
        for folder, files in folders.items():
            by_album[(norm(al["artist"]), norm(title))].append((key, folder, files, v))
    album_dups = 0
    for (art, tit), copies in by_album.items():
        if len(copies) < 2:
            continue
        # keep the copy with the most tracks, then best quality
        copies.sort(key=lambda c: (len(c[2]), max(quality(f) for f in c[2])), reverse=True)
        keep = copies[0]
        keep_titles = {norm(t[1]) for t in keep[3]["t"]}
        for c in copies[1:]:
            titles = {norm(t[1]) for t in c[3]["t"]}
            overlap = len(titles & keep_titles) / max(1, min(len(titles), len(keep_titles)))
            if overlap < 0.6:
                continue          # different tracklist — probably not the same album
            groups += 1; album_dups += 1
            al = albums[keep[0]]
            better = max(quality(f) for f in c[2]) > max(quality(f) for f in keep[2])
            note = " — NOTE: this copy is higher quality but has fewer tracks; check before deleting" if better else ""
            rows.append(["ALBUM COPY", groups, "KEEP", al["artist"], al["title"] or al.get("folder", ""), "", len(keep[2]),
                         max(f[3] for f in keep[2]), sum(f[2] for f in keep[2]) // 1048576, keep[1], ""])
            for f in c[2]:
                flagged.add(f[1])
                rows.append(["ALBUM COPY", groups, "DELETE", al["artist"], al["title"] or al.get("folder", ""), Path(f[1]).name,
                             len(c[2]), f[3], f[2] // 1048576, f[1], f"same album as {keep[1]} ({overlap:.0%} of tracks match){note}"])

    # ---------- 2. track copies inside one Plex album ----------
    track_dups = 0
    for key, v in cache.items():
        al = albums.get(key)
        if not al or not v.get("files"):
            continue
        seen = defaultdict(list)
        for t, f in zip(v["t"], v["files"]):
            if f[1] and f[1] not in flagged:
                seen[norm(t[1])].append((t, f))
        for nt, items in seen.items():
            if len(items) < 2 or not nt:
                continue
            # split by length: copies must be within 5s (or 3%) of each other
            items.sort(key=lambda it: -quality(it[1])[1])
            clusters = []
            for it in items:
                d = it[0][2]
                for cl in clusters:
                    if abs(cl[0][0][2] - d) <= max(5, 0.03 * max(d, cl[0][0][2])):
                        cl.append(it); break
                else:
                    clusters.append([it])
            for cl in clusters:
                if len(cl) < 2:
                    continue
                cl.sort(key=lambda it: quality(it[1]), reverse=True)
                groups += 1; track_dups += len(cl) - 1
                for i, (t, f) in enumerate(cl):
                    if i: flagged.add(f[1])
                    rows.append(["TRACK COPY", groups, "KEEP" if i == 0 else "DELETE", al["artist"],
                                 al["title"] or al.get("folder", ""), t[1], "", f[3], f[2] // 1048576, f[1],
                                 "" if i == 0 else f"same as {Path(cl[0][1][1]).name} ({f[4]} {f[3]} kbps vs {cl[0][1][4]} {cl[0][1][3]} kbps)"])

    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["type", "group", "action", "artist", "album", "track", "tracks_in_copy", "kbps", "MB", "file", "why"])
        w.writerows(rows)
    dele = [r for r in rows if r[2] == "DELETE"]
    mb = sum(r[8] for r in dele)
    print(f"Album copies: {album_dups} duplicate folders   Track copies: {track_dups} duplicate files")
    print(f"{len(dele)} files marked DELETE ({mb/1024:.1f} GB) — review {OUT.name} before doing anything")

    if not a.move:
        return
    # ---------- move DELETE files into <root>/_duplicates/<same sub-path> ----------
    # Re-read the CSV so any rows you removed or changed to KEEP in Excel are honoured.
    with OUT.open(encoding="utf-8-sig") as fh:
        dele = [r for r in csv.reader(fh)][1:]
    dele = [r for r in dele if len(r) >= 11 and r[2].strip().upper() == "DELETE"]
    if a.exact or a.min_match:
        need = 100 if a.exact else a.min_match
        def pct(r):
            m = re.search(r"\((\d+)% of tracks match\)", r[10]); return int(m.group(1)) if m else -1
        before = len(dele)
        dele = [r for r in dele if r[0] == "ALBUM COPY" and pct(r) >= need and "NOTE" not in r[10]]
        print(f"Filter: {len(dele)} of {before} DELETE rows are album copies with ≥{need}% match and no NOTE")
    if not dele:
        sys.exit("Nothing to move.")
    paths = [local(r[9]) for r in dele]
    root = os.path.commonpath(paths) if len(paths) > 1 else str(Path(paths[0]).parent)
    dest_root = Path(root) / "_duplicates"
    probe = Path(paths[0])
    if not probe.exists() and not probe.parent.exists():
        sys.exit(f"Can't see {probe.parent} from this PC.\n"
                 f"If Plex runs on a NAS, pass --map, e.g.  --map \"{r9prefix(dele[0][9])}=\\\\NAS-NAME\\PLEX\"  "
                 f"(open the share in Explorer to see its exact name, or use a mapped drive letter like P:)")
    print(f"\nMoving {len(paths)} files into {dest_root}{' (dry run)' if a.dry_run else ''}")
    moved = missing = 0
    for p in paths:
        src = Path(p)
        if not src.exists():
            missing += 1
            if missing <= 3: print("   not found:", src)
            continue
        dest = dest_root / src.relative_to(root)
        if a.dry_run:
            print("  ", src, "->", dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        moved += 1
    print(f"{moved} moved, {missing} not found on this machine (is the library on a different PC/NAS path?)")
    print("Now in Plex: library ⋯ → Scan Library Files, then ⋯ → Empty Trash. Delete _duplicates when you're happy.")


if __name__ == "__main__":
    main()
