# savveb

A tiny, low-dependency tool for **archiving websites and replaying them later**.

**The folder is the archive.** A list page (`index.html`), a spreadsheet of what
you keep (`manifest.csv`), the archive files (`wacz/`), and the player (`replay/`)
all live in one folder. Copy it to a USB stick or publish it on GitHub Pages and it
keeps working — no database, no server, no account.

Files are saved as [WACZ](https://specs.webrecorder.net/wacz/latest/) (WARC inside,
ISO 28500), so they stay readable by other web-archive tools long after this one.

[한국어 설명서 →](README.ko.md)

## Start your own archive

1. Click **Use this template** on GitHub (or download this folder).
2. Edit `savveb.json` — the title and description of your archive.
3. Delete the demo row in `manifest.csv` and `wacz/demo/`.

```bash
python3 archive.py doctor            # check what's installed
python3 archive.py add https://example.com --title "Example" --collection 2026
python3 archive.py capture --install # capture everything waiting (installs Playwright once)
python3 archive.py view --all        # review: replay each capture
```

After you've checked a capture, set its `status` to `ok` (or `partial`) in
`manifest.csv`. Only those rows appear in the public list.

## Publish

Push the folder to GitHub and turn on **Settings → Pages → Deploy from branch (main, /)**.
The list is then at `https://<you>.github.io/<repo>/`. Any static host that supports
HTTP range requests works the same way.

Replay uses a service worker, so the pages must be served over http(s) —
`python3 archive.py view` locally, or a static host. Opening `index.html` by
double-clicking will not replay.

## Just replay a file

`play.html` replays any `.wacz` / `.warc` you give it: drop a file on the page
(it stays in your browser) or paste a URL. Once published, it's a public player:

```
https://<you>.github.io/<repo>/play.html?source=<url-of-a-wacz>
```

Optional parameters: `url` (page to open inside the archive), `title`, `meta`.

## Commands

| Command | What it does |
|---|---|
| `add URL [--title --creator --collection]` | Add a row to `manifest.csv` |
| `capture [--match TEXT] [--all] [-y]` | Capture rows that are `pending`, `ready-to-capture` or `recapture-needed` |
| `view [--all] [--play]` | Serve the folder and open the list (or the player) |
| `edit` | Open a local form for editing `manifest.csv` |
| `check [--quick]` | Validate `manifest.csv`; verify every WACZ against its sha256 |
| `doctor` | Show what's installed |

Capture options live in `savveb.json` (`capture.page_limit`, `capture.depth`):
the crawler follows links under the starting URL's path, up to that many pages and
clicks deep. Large images are downscaled while capturing; set `ARCHIVE_OPTIMIZE=0`
to keep originals.

## manifest.csv

| Column | Filled by | Meaning |
|---|---|---|
| `title` | you | Name of the site |
| `creator` | you | Who made it |
| `collection` | you | Group (class, semester, project…). Also the folder under `wacz/` |
| `original_url` | you | Address to capture |
| `status` | you / capture | See below |
| `notes`, `link` | you | Free text; an extra link (e.g. source files) |
| `wacz_file`, `archived_date`, `sha256` | capture | Result of the last capture |

| status | Meaning | Public |
|---|---|---|
| `pending`, `ready-to-capture` | Waiting for capture | no |
| `review-needed` | Captured; a person should check the replay | no |
| `ok` / `partial` | Checked / checked with known gaps | **yes** |
| `recapture-needed` | Capture again on the next run | no |
| `private`, `hidden` | Never shown or captured | no |

Column labels in the list can be renamed in `savveb.json` → `labels`
(e.g. `"creator": "Student"`, `"collection": "Semester"`). Older manifests with
`student_name` / `semester` / `drive_link` columns are read as-is.

## Optional: an intake sheet

If other people submit sites, put a Google Sheet (or any CSV URL) in
`savveb.json` → `intake_sheet`. The sheet needs columns for the URL
(`url`/`link`/`original_url`) and optionally `title`, `creator`, `collection`.
Share it as "anyone with the link can view". Each `capture` adds rows that are new
to `manifest.csv` and never overwrites what's already there.

## Sites that don't capture well

The built-in crawler records what a real browser loads while visiting each page
and scrolling. Heavily interactive sites (games, things that load on click) may
need a manual capture with [ArchiveWeb.page](https://webrecorder.net/archivewebpage):
save the WACZ as `wacz/<collection>/<file>.wacz` and fill in `wacz_file`.

## Long-term care

- Keep at least two copies of the folder. A WACZ is self-contained; copying is enough.
- Run `python3 archive.py check` after copying — it verifies every file's checksum.
- If browsers someday can't run the bundled player, the WACZ files still open in
  any WARC tool. The archive files are what matter.

## Requirements

- Viewing: Python 3.9+ (standard library) or any static web host.
- Capturing: `playwright`, `warcio`, `wacz`, `pillow` and Playwright's Chromium.
  `python3 archive.py capture --install` installs them.

## License

MIT for this project's code (`LICENSE`). The bundled player in `replay/` is
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6 by Webrecorder,
AGPL-3.0-or-later (`replay/LICENSE.replaywebpage.txt`), included unmodified.
