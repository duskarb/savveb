# savveb

**웹사이트를 보관하고, 어디서든 재생하세요.**

명령 한 줄로 웹사이트 전체를 `.wacz` 파일 하나에 담습니다. 그 파일을
[duskarb.github.io/savveb](https://duskarb.github.io/savveb/)에서 열거나 `savveb play`로 열면,
페이지·이미지·폰트·링크까지 원래 사이트 그대로 돌아옵니다.

[데모 보기](https://duskarb.github.io/savveb/?source=demo/yeonamkyu.com-2026-10-18.wacz&url=https%3A%2F%2Fwww.yeonamkyu.com%2Fworks&title=yeonamkyu.com) ·
[English](README.md)

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

## 설치

Python 3.9 이상과 [pipx](https://pipx.pypa.io/)가 필요합니다.

```bash
pipx install git+https://github.com/duskarb/savveb
```

- pipx가 없다면 `brew install pipx`(macOS) 또는 `python3 -m pip install --user pipx`로
  설치하고, `pipx ensurepath` 후 터미널을 새로 여세요.
- 처음 `savveb save`를 실행하면 Playwright용 Chromium(약 100MB) 설치를 한 번 묻습니다.
- 업데이트: `pipx reinstall savveb` (`pipx upgrade`로는 새 버전을 못 받습니다).

## 보관

```bash
savveb save https://내-사이트.example/
```

현재 폴더에 `내-사이트.example-<날짜>.wacz`가 생깁니다.

| 옵션 | 기본값 | |
|---|---|---|
| `-o 파일` | `<사이트>-<날짜>.wacz` | 저장할 파일 |
| `--pages N` | 500 | 최대 저장 페이지 수. 더 찾았는데 못 담았으면 알려 줍니다 |
| `--depth N` | 20 | 링크를 따라갈 깊이 |
| `--parallel N` | 4 | 동시에 여는 페이지 수. 작은 서버라면 1로 천천히 |
| `--no-optimize` | 끔 | 큰 이미지를 그대로 둡니다 |

빠진 페이지가 있으면 주소를 더 적으세요: `savveb save https://사이트/ https://사이트/숨은-페이지`

### 페이지를 찾는 방법

시작 주소의 경로 아래에 있는 페이지를 찾습니다. 리다이렉트를 따라가므로
`site.com` → `www.site.com`도 괜찮습니다.

- 각 페이지의 링크
- `sitemap.xml`
- 주소를 바꾸는 버튼과 탭. React, Next.js, Vue 같은 SPA에는 일반 링크가 없는 경우가 많습니다.

### 저장되는 것

- 실제 브라우저가 각 페이지를 열고 끝까지 스크롤하는 동안 받는 모든 것.
  그래서 JavaScript로 만든 사이트도 잘 재생됩니다.
- 화면 크기별 이미지(`srcset`): 한 벌만 저장하고 나머지 크기는 그 파일을 가리키게 해서,
  어떤 화면에서도 이미지가 보입니다.
- 열리지 않고 다운로드되는 파일(PDF 등).
- 큰 이미지는 2000px로 줄여 다시 압축합니다(`--no-optimize`로 끌 수 있습니다).
- 광고, 방문자 분석, 추적 스크립트는 받지 않습니다. 저장을 느리게 하고 파일만 키우며,
  아카이브에서는 어차피 동작하지 않기 때문입니다.

### 잘 안 담길 수 있는 것

- 로그인해야 보이는 페이지
- 마우스를 올리거나 끌거나 입력해야 나오는 내용, 10초 넘게 이어지는 무한 스크롤
- CSS에서 고르는 화면 크기별 이미지(`image-set()`, 미디어 쿼리)
- 스트리밍 영상, 실시간 데이터, 서버에 묻는 검색창과 입력 폼
- 자동화 브라우저를 막는 사이트

이런 경우에는 [ArchiveWeb.page](https://webrecorder.net/archivewebpage)로 직접 둘러보며
녹화할 수 있고, 그 파일도 savveb에서 재생됩니다.

## 재생

- **웹에서:** [duskarb.github.io/savveb](https://duskarb.github.io/savveb/)에 파일을 끌어다 놓으세요.
  업로드되지 않고 브라우저 안에서만 열립니다.
- **오프라인:** `savveb play 내-사이트.example-2026-01-01.wacz`
- **링크로 공유:** `.wacz`를 다른 사이트에서 Range 요청으로 읽을 수 있는 곳(GitHub Pages 등)에 올리고
  `https://duskarb.github.io/savveb/?source=<wacz 주소>`를 공유하세요.
  `&url=<페이지>`를 붙이면 페이지 목록 대신 그 페이지가 바로 열립니다.

다른 웹 아카이브 도구로 만든 WACZ·WARC도 재생됩니다.

## 보관 파일 관리

`.wacz`는 표준 [WACZ](https://specs.webrecorder.net/wacz/latest/) 파일입니다. 사이트의
WARC(ISO 28500), 색인, 체크섬이 든 zip이라 다른 웹 아카이브 도구로도 읽을 수 있습니다.
다른 파일처럼 폴더, 드라이브, 저장소에 보관하면 됩니다. 여러 사이트를 어떻게 정리할지는
각자 정하세요.

## 개발

```bash
git clone https://github.com/duskarb/savveb && cd savveb
python3 -m pip install -e .
python3 -m savveb save https://example.com/
```

`docs/`는 웹사이트입니다(GitHub Pages, `main` / `docs`). 재생에 필요한 파일은
`savveb play`용으로 패키지에도 들어갑니다.

## 변경 기록

- **0.3.2** — Next.js 페이지 데이터처럼 charset이 없는 텍스트 응답의 한글이 깨지던 문제 수정.
  이전에 만든 아카이브는 다시 저장해야 합니다.
- **0.3.1** — 웹사이트 한국어/영어 지원, yeonamkyu.com 데모, 문서 정리.
- **0.3.0** — Adobe Fonts(Typekit) 등 바이너리로 불러오는 폰트도 재생(재생기 수정, 이미 저장한
  아카이브에도 적용). 화면 크기별 이미지가 깨지지 않음.
- **0.2.0** — 약 6배 빨라짐(탭 병렬, 똑똑한 대기). 광고·추적 스크립트 제외, PDF 저장.
- **0.1.0** — `save`와 `play`.

## 라이선스

MIT(`LICENSE`). `docs/replay/`의 재생기는 Webrecorder의
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6(AGPL-3.0-or-later,
`docs/replay/LICENSE.replaywebpage.txt`)이고, 작은 수정 하나를 `docs/replay/README.md`에
적어 두었습니다.
