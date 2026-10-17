# savveb

**Save a website. Replay it anywhere.**

One command saves a whole website into a single `.wacz` file. Open that file on
[duskarb.github.io/savveb](https://duskarb.github.io/savveb/) or with `savveb play`,
and the site comes back as it was — pages, images, fonts, working links.

[Try a demo](https://duskarb.github.io/savveb/?source=demo/yeonamkyu.com-2026-10-18.wacz&url=https%3A%2F%2Fwww.yeonamkyu.com%2Fworks&title=yeonamkyu.com) ·
[한국어](README.ko.md)

```
$ savveb save https://www.yeonamkyu.com/

  ʕ•ᴥ•ʔ  savveb 0.3.2
  saving https://www.yeonamkyu.com/

      1  https://www.yeonamkyu.com/
      2  https://www.yeonamkyu.com/works
      3  https://www.yeonamkyu.com/notes
    …
     52  https://www.yeonamkyu.com/notes/furniture

  ʕ•̀ᴥ•́ʔ✧  saved 52 pages · 987 files · 10.5 MB · 25s
         → www.yeonamkyu.com-2026-10-18.wacz
```

## Install

Needs Python 3.9+ and [pipx](https://pipx.pypa.io/).

```bash
pipx install git+https://github.com/duskarb/savveb
```

- No pipx? `brew install pipx` (macOS) or `python3 -m pip install --user pipx`,
  then `pipx ensurepath` and open a new terminal.
- The first `savveb save` offers to install Playwright's Chromium (~100 MB), once.
- Update: `pipx reinstall savveb` (`pipx upgrade` does not see new commits).

## Save

```bash
savveb save https://your-site.example/
```

You get `your-site.example-<date>.wacz` in the current folder.

| Option | Default | |
|---|---|---|
| `-o FILE` | `<site>-<date>.wacz` | where to write |
| `--pages N` | 500 | most pages to save; savveb tells you if it found more |
| `--depth N` | 20 | how many links deep to follow |
| `--parallel N` | 4 | pages to load at once; use 1 to go easy on small servers |
| `--no-optimize` | off | keep large images as they are |

If a page is missed, add its address: `savveb save https://site.example/ https://site.example/hidden`.

### How it finds pages

Everything under the start URL's path (after redirects, so `site.com` → `www.site.com` works):

- links on each page,
- `sitemap.xml`,
- buttons and tabs that change the address — single-page apps (React, Next.js, Vue…)
  often have no ordinary links.

### What it saves

- Everything a real browser loads while opening each page and scrolling to the bottom,
  so JavaScript-heavy sites replay well.
- Responsive images (`srcset`): one size is kept and the other sizes point to it, so
  images show on any screen without storing every size.
- Files that download instead of opening, such as PDFs.
- Large images are downscaled to 2000 px and recompressed (`--no-optimize` to keep them).
- Ads, analytics and trackers are skipped: they slow saving, bloat files and don't work
  in an archive anyway.

### What may not come out right

- Pages behind a login.
- Content that only appears on hover, drag or typing, and infinite scroll past ~10 seconds.
- Responsive images chosen in CSS (`image-set()`, media queries).
- Streaming video, live data, search boxes and forms that ask a server.
- Sites that block automated browsers.

For these, [ArchiveWeb.page](https://webrecorder.net/archivewebpage) lets you record by
hand as you browse; its files play here too.

## Replay

- **On the web:** drop the file on [duskarb.github.io/savveb](https://duskarb.github.io/savveb/).
  It opens in your browser and is never uploaded.
- **Offline:** `savveb play your-site.example-2026-01-01.wacz`
- **Share a link:** put the `.wacz` anywhere that allows cross-origin range requests
  (GitHub Pages does), then share `https://duskarb.github.io/savveb/?source=<url-of-the-wacz>`.
  Add `&url=<page>` to open a specific page instead of the page list.

Any WACZ or WARC plays, including files made with other web-archive tools.

## Keeping archives

A `.wacz` is a standard [WACZ](https://specs.webrecorder.net/wacz/latest/) file: a zip
with the site's WARC (ISO 28500), an index and checksums, readable by other web-archive
tools. Keep it like any other file — a folder, a drive, a repo. Organizing many sites is
up to you.

## Develop

```bash
git clone https://github.com/duskarb/savveb && cd savveb
python3 -m pip install -e .
python3 -m savveb save https://example.com/
```

`docs/` is the website (GitHub Pages, from `main` / `docs`). Its player files are also
bundled into the package for `savveb play`.

## Changes

- **0.3.2** — Korean and other UTF-8 text in Next.js page data (and any text response
  without a charset) is no longer garbled. Re-save archives made before.
- **0.3.1** — Website in Korean and English, yeonamkyu.com demo; clearer docs.
- **0.3.0** — Fonts from Adobe Fonts (Typekit) and other byte-loaded fonts replay
  (player fix, also for archives saved earlier). Responsive images no longer break.
- **0.2.0** — About 6× faster (parallel tabs, smarter waits); ads and trackers skipped;
  PDFs saved.
- **0.1.0** — `save` and `play`.

## License

MIT (`LICENSE`). The player in `docs/replay/` is
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6 by Webrecorder,
AGPL-3.0-or-later (`docs/replay/LICENSE.replaywebpage.txt`), with one small fix described in
`docs/replay/README.md`.
