# savveb

**Save a website. Replay it anywhere.**

`savveb save` turns a website into one `.wacz` file. Drop that file on
[duskarb.github.io/savveb](https://duskarb.github.io/savveb/), or run `savveb play`,
and the site comes back as it was, working links and all.

[한국어 →](README.ko.md)

## Save

Needs Python 3.9+ and [pipx](https://pipx.pypa.io/).

```bash
pipx install git+https://github.com/duskarb/savveb
savveb save https://your-site.example/
```

You get `your-site.example-<date>.wacz` in the current folder. The first run asks
to install Playwright's Chromium (~100 MB) once.

savveb opens each page in a real browser, scrolls it, and records everything the
browser loads, so sites built with JavaScript come out right. It finds the site's
pages under the starting URL's path by following links, reading `sitemap.xml`, and
clicking menu buttons that change the address (single-page apps built with React,
Next.js and similar often have no ordinary links). If a page still gets missed, add
its address: `savveb save https://site.example/ https://site.example/hidden-page`.

| Option | Default | |
|---|---|---|
| `-o FILE` | `<site>-<date>.wacz` | where to write |
| `--pages N` | 500 | most pages to save; savveb tells you if it found more |
| `--depth N` | 20 | how many links deep to follow |
| `--no-optimize` | off | keep large images as they are (by default images over 300 KB are downscaled to 2000 px) |

## Replay

- **On the web:** drop the file on [duskarb.github.io/savveb](https://duskarb.github.io/savveb/).
  It opens in your browser and is never uploaded.
- **Offline:** `savveb play your-site.example-2026-01-01.wacz`
- **Link to it:** put the `.wacz` anywhere that serves files with CORS and range requests
  (GitHub Pages does), then share
  `https://duskarb.github.io/savveb/?source=<url-of-the-wacz>`.
  Add `&url=<page>` to open a specific page instead of the page list.

Any WACZ or WARC plays, including files made with other tools such as
[ArchiveWeb.page](https://webrecorder.net/archivewebpage), a browser extension that
records as you browse by hand. savveb is for the opposite: give it a URL and it
visits the whole site on its own, from one command or a script.

## Keeping archives

A `.wacz` is a standard [WACZ](https://specs.webrecorder.net/wacz/latest/) file: a zip
with the site's WARC (ISO 28500), an index and checksums. Keep it like any other file —
in a folder, a drive, a repo. If you archive many sites, how you organize them is up to you.

## Develop

```bash
git clone https://github.com/duskarb/savveb && cd savveb
python3 -m pip install -e .
python3 -m savveb save https://example.com/
```

`docs/` is the website (served by GitHub Pages) and is bundled into the package as the
player for `savveb play`.

## License

MIT (`LICENSE`). The player in `docs/replay/` is
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6 by Webrecorder,
AGPL-3.0-or-later (`docs/replay/LICENSE.replaywebpage.txt`), included unmodified.
