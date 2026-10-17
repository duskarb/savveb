# savveb

**웹사이트를 보관하고, 어디서든 재생한다.**

`savveb save`는 웹사이트를 `.wacz` 파일 하나로 만든다. 그 파일을
[duskarb.github.io/savveb](https://duskarb.github.io/savveb/)에 끌어다 놓거나 `savveb play`로
열면, 링크까지 살아 있는 원래 사이트 그대로 재생된다.

## 보관

Python 3.9 이상과 [pipx](https://pipx.pypa.io/)가 필요하다.

```bash
pipx install git+https://github.com/duskarb/savveb
savveb save https://내-사이트.example/
```

pipx가 없으면 `brew install pipx`(macOS) 또는 `python3 -m pip install --user pipx`로 설치하고
`pipx ensurepath` 후 터미널을 새로 연다.

나중에 업데이트하려면 `pipx reinstall savveb`.

현재 폴더에 `내-사이트.example-<날짜>.wacz`가 생긴다. 처음 실행할 때 Playwright용
Chromium(약 100MB)을 한 번 설치할지 묻는다.

savveb는 실제 브라우저로 각 페이지를 열고 스크롤하면서 브라우저가 받은 것을 모두
기록한다. 그래서 JavaScript로 만든 사이트도 잘 담긴다. 시작 URL 경로 아래의 페이지를
링크, `sitemap.xml`, 그리고 주소를 바꾸는 메뉴 버튼을 눌러 보는 방식으로 찾는다
(React, Next.js 같은 SPA는 일반 링크가 없는 경우가 많다). 그래도 빠지는 페이지가 있으면
주소를 더 적으면 된다: `savveb save https://사이트/ https://사이트/숨은-페이지`
광고, 방문자 분석, 추적 스크립트는 받지 않는다. 저장을 느리게 하고 파일만 키우며,
아카이브에서는 어차피 동작하지 않기 때문이다.

| 옵션 | 기본값 | |
|---|---|---|
| `-o 파일` | `<사이트>-<날짜>.wacz` | 저장할 파일 |
| `--pages N` | 500 | 최대 저장 페이지 수. 더 찾았는데 못 담았으면 알려 준다 |
| `--depth N` | 20 | 링크를 따라갈 깊이 |
| `--parallel N` | 4 | 동시에 여는 페이지 수 |
| `--no-optimize` | 끔 | 큰 이미지를 그대로 둔다 (기본은 300KB 넘는 이미지를 2000px로 줄임) |

## 재생

- **웹에서:** [duskarb.github.io/savveb](https://duskarb.github.io/savveb/)에 파일을 끌어다 놓는다.
  업로드되지 않고 브라우저 안에서만 열린다.
- **오프라인:** `savveb play 내-사이트.example-2026-01-01.wacz`
- **링크로 공유:** `.wacz`를 CORS와 Range 요청을 지원하는 곳(GitHub Pages 등)에 올리고
  `https://duskarb.github.io/savveb/?source=<wacz 주소>`를 공유한다.
  `&url=<페이지>`를 붙이면 페이지 목록 대신 그 페이지가 바로 열린다.

다른 도구로 만든 WACZ/WARC도 재생된다. [ArchiveWeb.page](https://webrecorder.net/archivewebpage)는
사람이 직접 둘러보며 녹화하는 브라우저 확장이고, savveb는 반대로 URL만 주면 사이트 전체를
알아서 돌아다니며 담는다. 명령 한 줄이나 스크립트로 돌릴 수 있다.

## 보관 파일 관리

`.wacz`는 표준 [WACZ](https://specs.webrecorder.net/wacz/latest/) 파일이다. 사이트의
WARC(ISO 28500), 색인, 체크섬이 든 zip이다. 다른 파일처럼 폴더, 드라이브, 저장소에
보관하면 된다. 여러 사이트를 어떻게 정리할지는 각자 정하면 된다.

## 라이선스

MIT(`LICENSE`). `docs/replay/`의 재생기는 Webrecorder의
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6이며
AGPL-3.0-or-later(`docs/replay/LICENSE.replaywebpage.txt`)로, 수정 없이 포함했다.
