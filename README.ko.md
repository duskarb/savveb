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

현재 폴더에 `내-사이트.example-<날짜>.wacz`가 생긴다. 처음 실행할 때 Playwright용
Chromium(약 100MB)을 한 번 설치할지 묻는다.

savveb는 실제 브라우저로 각 페이지를 열고 스크롤하면서 브라우저가 받은 것을 모두
기록한다. 그래서 JavaScript로 만든 사이트도 잘 담긴다. 시작 URL 경로 아래의 링크를 따라간다.

| 옵션 | 기본값 | |
|---|---|---|
| `-o 파일` | `<사이트>-<날짜>.wacz` | 저장할 파일 |
| `--pages N` | 30 | 최대 방문 페이지 수 |
| `--depth N` | 3 | 링크를 따라갈 깊이 |
| `--no-optimize` | 끔 | 큰 이미지를 그대로 둔다 (기본은 300KB 넘는 이미지를 2000px로 줄임) |

## 재생

- **웹에서:** [duskarb.github.io/savveb](https://duskarb.github.io/savveb/)에 파일을 끌어다 놓는다.
  업로드되지 않고 브라우저 안에서만 열린다.
- **오프라인:** `savveb play 내-사이트.example-2026-01-01.wacz`
- **링크로 공유:** `.wacz`를 CORS와 Range 요청을 지원하는 곳(GitHub Pages 등)에 올리고
  `https://duskarb.github.io/savveb/?source=<wacz 주소>`를 공유한다.
  `&url=<페이지>`를 붙이면 페이지 목록 대신 그 페이지가 바로 열린다.

다른 도구로 만든 WACZ/WARC도 재생된다. 클릭해야 내용이 나오는 사이트는
[ArchiveWeb.page](https://webrecorder.net/archivewebpage)로 직접 둘러보며 저장하면 좋다.

## 보관 파일 관리

`.wacz`는 표준 [WACZ](https://specs.webrecorder.net/wacz/latest/) 파일이다. 사이트의
WARC(ISO 28500), 색인, 체크섬이 든 zip이다. 다른 파일처럼 폴더, 드라이브, 저장소에
보관하면 된다. 여러 사이트를 어떻게 정리할지는 각자 정하면 된다.

## 라이선스

MIT(`LICENSE`). `docs/replay/`의 재생기는 Webrecorder의
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6이며
AGPL-3.0-or-later(`docs/replay/LICENSE.replaywebpage.txt`)로, 수정 없이 포함했다.
