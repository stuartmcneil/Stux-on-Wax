# Stux on Wax

A catalogue of [Stuart McNeil](https://stuartmcneil.github.io/window/)'s vinyl collection and how much of it has been digitised into Plex.

**Live page:** enable GitHub Pages (Settings → Pages → Deploy from branch → `main` / root) and open `https://<your-username>.github.io/<repo-name>/`.
Or just open `index.html` locally.

## What's here

| File | What it is |
|---|---|
| `index.html` | The catalogue page — 978 releases from the [Discogs collection](https://www.discogs.com/user/stuartmcneil/collection), with a Shelf / Ripping / In Plex status and notes per record. Self-contained; cover art is pulled from Discogs. |
| `progress.json` | The digitisation status. The page loads this automatically when served from GitHub Pages, so commit it whenever it changes (use **Back up progress** on the page, save over this file). |
| `discogs_collection_snapshot.csv` | Plain CSV of the collection as fetched on 2 Sep 2026. |
| `vinyl_digitizer.py` | Script that splits a recorded side into tracks, tags them from MusicBrainz and embeds artwork. |

Audio files (`*.wav`, `*.mp3`, `digitized_vinyl/`) are ignored by git and stay on the local machine.

## Keeping it up to date

1. **New records:** Discogs → `https://www.discogs.com/users/export` → Collection → Request Data Export → Download, then **Import Discogs CSV** on the page.
2. **Progress:** mark records on the page, click **Back up progress**, save the download as `progress.json` in this folder, commit and push.

Status is also kept in the browser's local storage as a fallback, so a page opened from disk still remembers what you clicked.
