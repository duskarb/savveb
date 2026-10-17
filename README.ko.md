# archivve

웹사이트를 **보존(캡처)하고 나중에 그대로 재생**하는 아주 단순한 도구.

**이 폴더가 곧 아카이브다.** 목록 페이지(`index.html`), 명단(`manifest.csv`),
아카이브 파일(`wacz/`), 재생기(`replay/`)가 한 폴더에 다 들어 있다. USB에 복사하든
GitHub Pages에 올리든 그대로 동작한다. 데이터베이스·서버·계정이 필요 없다.

파일은 [WACZ](https://specs.webrecorder.net/wacz/latest/)(안에 WARC, ISO 28500)로
저장되므로, 이 도구가 없어져도 다른 웹 아카이브 도구로 열 수 있다.

## 내 아카이브 시작하기

1. GitHub에서 **Use this template**을 누른다 (또는 이 폴더를 내려받는다).
2. `archivve.json`에서 아카이브 제목·설명을 바꾼다.
3. `manifest.csv`의 데모 행과 `wacz/demo/`를 지운다.

```bash
python3 archive.py doctor            # 설치 상태 확인
python3 archive.py add https://example.com --title "Example" --collection 2026
python3 archive.py capture --install # 대기 중인 항목 캡처 (처음 한 번 Playwright 설치)
python3 archive.py view --all        # 검수: 캡처본을 하나씩 재생해 본다
```

재생을 확인한 항목은 `manifest.csv`에서 `status`를 `ok`(또는 `partial`)로 바꾼다.
공개 목록에는 이 두 상태만 보인다.

## 공개하기

폴더를 GitHub에 올리고 **Settings → Pages → Deploy from branch (main, /)** 를 켠다.
목록은 `https://<계정>.github.io/<저장소>/`에서 보인다. HTTP Range 요청을 지원하는
정적 호스팅이면 어디든 똑같이 동작한다.

재생기는 서비스워커를 쓰므로 반드시 http(s)로 열어야 한다 — 로컬에서는
`python3 archive.py view`, 아니면 정적 호스팅. `index.html`을 더블클릭하면 재생되지 않는다.

## 파일 하나만 재생하기

`play.html`은 어떤 `.wacz` / `.warc` 든 재생한다. 파일을 끌어다 놓거나(업로드되지 않고
브라우저 안에서만 열림) URL을 붙여 넣는다. 공개해 두면 누구나 쓰는 재생기가 된다:

```
https://<계정>.github.io/<저장소>/play.html?source=<wacz 주소>
```

선택 파라미터: `url`(아카이브 안에서 처음 열 페이지), `title`, `meta`.

## 명령어

| 명령 | 하는 일 |
|---|---|
| `add URL [--title --creator --collection]` | `manifest.csv`에 한 줄 추가 |
| `capture [--match 글자] [--all] [-y]` | `pending`·`ready-to-capture`·`recapture-needed` 행을 캡처 |
| `view [--all] [--play]` | 폴더를 로컬 서버로 띄우고 목록(또는 재생기)을 연다 |
| `edit` | `manifest.csv` 편집용 로컬 폼 열기 |
| `check [--quick]` | `manifest.csv` 검사 + 모든 WACZ를 sha256으로 무결성 확인 |
| `doctor` | 설치 상태 확인 |

캡처 범위는 `archivve.json`의 `capture.page_limit`, `capture.depth`로 정한다. 시작 URL의
경로 아래 링크를 그 페이지 수·깊이만큼 따라간다. 큰 이미지는 캡처하면서 줄이며,
원본을 유지하려면 `ARCHIVE_OPTIMIZE=0`.

## manifest.csv

| 칸 | 누가 채우나 | 의미 |
|---|---|---|
| `title` | 사람 | 사이트 이름 |
| `creator` | 사람 | 만든 사람 |
| `collection` | 사람 | 묶음(수업·학기·프로젝트…). `wacz/` 아래 폴더 이름도 된다 |
| `original_url` | 사람 | 캡처할 주소 |
| `status` | 사람 / 캡처 | 아래 표 |
| `notes`, `link` | 사람 | 메모, 추가 링크(예: 원본 파일) |
| `wacz_file`, `archived_date`, `sha256` | 캡처 | 마지막 캡처 결과 |

| status | 의미 | 공개 |
|---|---|---|
| `pending`, `ready-to-capture` | 캡처 대기 | 아니오 |
| `review-needed` | 캡처됨, 사람이 재생 확인 필요 | 아니오 |
| `ok` / `partial` | 확인 완료 / 일부 누락 있지만 공개 가능 | **예** |
| `recapture-needed` | 다음 실행 때 다시 캡처 | 아니오 |
| `private`, `hidden` | 공개도 캡처도 안 함 | 아니오 |

목록의 칸 이름은 `archivve.json` → `labels`에서 바꿀 수 있다
(예: `"creator": "학생"`, `"collection": "학기"`). 예전 형식(`student_name` /
`semester` / `drive_link` 칸)의 manifest도 그대로 읽는다.

## 선택: 접수용 시트

여러 사람이 사이트를 제출한다면 구글 시트(또는 아무 CSV 주소)를 `archivve.json` →
`intake_sheet`에 넣는다. 시트에는 주소 칸(`url`/`link`/`original_url`/`링크`)과 선택적으로
`title`, `creator`, `collection` 칸이 있으면 된다. "링크가 있는 모든 사용자 보기"로 공유한다.
`capture`할 때마다 새 행만 `manifest.csv`에 추가하고, 이미 있는 내용은 절대 덮어쓰지 않는다.

## 잘 캡처되지 않는 사이트

내장 크롤러는 실제 브라우저가 페이지를 열고 스크롤하는 동안 받은 것을 기록한다.
클릭해야 로드되는 인터랙티브 작품은 [ArchiveWeb.page](https://webrecorder.net/archivewebpage)로
직접 캡처해 `wacz/<collection>/<파일>.wacz`로 넣고 `wacz_file`을 채운다.

## 장기 보존

- 폴더 사본을 두 벌 이상 둔다. WACZ는 자족적 파일이라 복사만으로 보존된다.
- 복사한 뒤 `python3 archive.py check`로 모든 파일의 체크섬을 확인한다.
- 먼 미래에 브라우저가 내장 재생기를 못 돌려도 WACZ는 어떤 WARC 도구로든 열린다.
  중요한 건 아카이브 파일이다.

## 라이선스

이 프로젝트 코드는 MIT(`LICENSE`). `replay/`에 들어 있는 재생기는 Webrecorder의
[ReplayWeb.page](https://github.com/webrecorder/replayweb.page) 2.4.6으로
AGPL-3.0-or-later(`replay/LICENSE.replaywebpage.txt`)이며 수정 없이 포함했다.
