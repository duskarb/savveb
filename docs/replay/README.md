# Replay Runtime

Pinned ReplayWeb.page runtime files:

- `ui.js`
- `sw.js`

Version: `replaywebpage@2.4.6`
License: `AGPL-3.0-or-later` (`LICENSE.replaywebpage.txt`)

Source:

- `https://cdn.jsdelivr.net/npm/replaywebpage@2.4.6/ui.js`
- `https://cdn.jsdelivr.net/npm/replaywebpage@2.4.6/sw.js`
- `https://cdn.jsdelivr.net/npm/replaywebpage@2.4.6/LICENSE`

The site and `savveb play` load these local files instead of a CDN so replay stays
stable even if ReplayWeb.page changes later.

## Local change

`sw.js` has one patch (the wombat `FontFace` override). Upstream turns a binary
font source (`ArrayBuffer` / `ArrayBufferView`) into the string
`"[object ArrayBuffer]"`, so fonts added from bytes fail in replay; this breaks
Adobe Fonts (Typekit) dynamic subsetting and other loaders that fetch font data
themselves. The patch passes non-string sources through unchanged:

```diff
-n="string"!=typeof i?r.rewriteInlineStyle(i.toString()):r.rewriteInlineStyle(i)
+n="string"!=typeof i?i:r.rewriteInlineStyle(i)
```

The same code is still in replaywebpage 2.5.3.
