# Codex 인수인계 — p.art_mag 일일 뉴스 발행

> 대상: Codex CLI (`codex exec`). 기존 Claude 클라우드 루틴(`daily-news-thumbnail`, 매일 16:07 KST)을
> **로컬 PC의 Codex + 윈도우 예약작업**으로 대체하기 위한 지침이다.
> 이 문서는 Codex가 읽는 실행 지침이자, 사람이 읽는 인수인계 문서다.

---

## 0. 왜 넘기나 / 무엇이 달라지나

| 항목 | 기존 (Claude 클라우드 루틴) | 이관 후 (Codex 로컬) |
|---|---|---|
| 실행 위치 | Anthropic 클라우드 (격리 세션) | 내 PC (`C:\Users\hyein\Documents\hyein-projects\art-tool`) |
| 주 실패 원인 | 5시간 세션 한도, 스케줄 지연(최대 7~8시간) | PC가 꺼져 있으면 미실행 (예약작업이 다음 로그온에 보충 실행) |
| 비용 | Claude 토큰 소모 | Codex(ChatGPT) 쿼터 소모 |
| Discord 전송 | `claude/*` 브랜치 푸시 → `discord-notify.yml` CI가 전송 | **동일 (변경 없음)** |

**바꾸지 않는 것**: 산출물 형식(PNG + JSON), 브랜치 네이밍(`claude/*`), CI 워크플로, Discord 웹훅.
CI(`discord-notify.yml`)가 `claude/*` 푸시에 트리거되므로 **Codex도 브랜치 이름을 `claude/`로
시작해야 한다.** (`codex/`로 바꾸면 Discord가 안 간다. 바꾸려면 워크플로 트리거도 같이 고쳐야 함.)

---

## 1. 사전 준비 (사람이 1회만)

```powershell
# 1) Codex 로그인 확인
codex login status

# 2) 웹 검색 활성화 — 뉴스 큐레이션에 필수.
#    %USERPROFILE%\.codex\config.toml 에 영구 설정 권장:
#    [tools]
#    web_search = true

# 3) 파이썬 의존성
cd C:\Users\hyein\Documents\hyein-projects\art-tool
pip install -r requirements.txt

# 4) 기존 Claude 클라우드 루틴 비활성화 (이중 발행 방지)
#    https://claude.ai/code/routines → daily-news-thumbnail → 끄기
```

⚠️ **이중 발행 주의**: Claude 루틴을 끄지 않고 Codex를 켜면 하루 4건이 나간다. 반드시 한쪽만 켤 것.
GitHub Actions 폴백(`daily-news.yml` 17:11/17:51/18:31)은 **그대로 둔다** — 스킵 가드가 있어
Codex가 이미 발행했으면 알아서 거른다.

---

## 2. Codex 실행 명령 (예약작업이 부를 명령)

```powershell
codex exec `
  -C "C:\Users\hyein\Documents\hyein-projects\art-tool" `
  -s workspace-write `
  -c tools.web_search=true `
  -c sandbox_workspace_write.network_access=true `
  --output-last-message "C:\Users\hyein\Documents\hyein-projects\art-tool\output\codex_last_run.txt" `
  "notes\CODEX_DAILY_NEWS.md 의 '3. 실행 절차'를 처음부터 끝까지 그대로 수행해라. 사용자 확인 없이 끝까지 자동 진행."
```

- `-s workspace-write` + `network_access=true` — 기사 파싱·이미지 다운로드·`git push`에 네트워크가 필요하다.
- `--output-last-message` — 예약작업으로 돌면 콘솔을 못 보니 마지막 보고를 파일로 남긴다.
- 실패 재현: 같은 명령을 터미널에서 그대로 실행.

러너 스크립트: `tools/run_daily_news_codex.ps1` (6절)

---

## 3. 실행 절차 (Codex가 따라야 할 본문)

> 규칙 정본은 저장소 루트 `CLAUDE.md`다. **작업 시작 전 반드시 `CLAUDE.md`를 읽어라.**
> 단계별 보조 문서:
> 큐레이션 `.claude/skills/daily-news/curation.md` ·
> 이미지 `.claude/skills/daily-news/image-rules.md` ·
> 헤드라인·캡션 `.claude/skills/daily-news/headline-caption.md`
>
> ⚠️ `SKILL (1).md`, `CLAUDE (1).md`, `daily_auto (1).py` 처럼 `(1)`이 붙은 파일은 **중복 사본이니
> 무시**하고 괄호 없는 원본만 읽어라.

### STEP 0 — 당일 중복 발행 검사 (제일 먼저)

오늘자 발행물이 `main` 또는 `claude/*` 브랜치에 하나라도 있으면 **아무것도 만들지 말고 즉시 종료**하고
"이미 발행 완료 — 스킵"만 보고한다.

```bash
git fetch -q origin main '+refs/heads/claude/*:refs/remotes/origin/claude/*' || true
TODAY=$(python -c "from datetime import date; print(date.today().isoformat())")
{ git ls-tree -r --name-only origin/main output/news
  for b in $(git for-each-ref --sort=-committerdate --count=5 \
      --format='%(refname:short)' refs/remotes/origin/claude/); do
    git ls-tree -r --name-only "$b" output/news
  done; } | grep "output/news/${TODAY}_" | sort -u
```

출력에 파일이 하나라도 나오면 → 즉시 종료 (STEP 1 이하 진행 금지).

### STEP 0.5 — 최근 30일 발행 이력 확인 (중복 소재 차단)

자동 발행분은 `main`에 머지되지 않고 `claude/*` 브랜치에만 쌓인다. main만 보면 어제 뭘 냈는지 모른 채
같은 전시를 또 고르게 된다. `.claude/skills/daily-news/SKILL.md`의 **STEP 0.5 파이썬 스니펫을
그대로 실행**해 최근 40개 `claude/*` 브랜치까지 훑어라.

**규칙(예외 없음)**: 그 목록의 작가명·전시명·기관명과 같거나 유사하면 즉시 탈락. 표기 변형도 동일
대상으로 본다 ("데미안 허스트" = "데이미언 허스트" = "Damien Hirst"). 전시가 진행 중이어도 이미
발행했으면 재선정 금지.

### STEP 1 — 오늘 날짜 확인

```bash
python -c "from datetime import date; d=date.today(); print(d.isoformat(), f'{d.month}월 {d.day}일')"
```

### STEP 2 — 후보 수집·선별 (`curation.md` 읽고 진행)

웹 검색으로 **8건 이상** 수집 → 하드 게이트 → 점수 평가 → **정확히 2건** 확정.

후보가 되려면 셋이 동시에 성립해야 한다:

1. **사건이 있다** — 결정·발표·데뷔·수상·등록·철수·회수·초청·개최·재개·논란.
   "지금 전시 중"은 사건이 아니다. 헤드라인이 동사로 끝나야 한다.
2. **아는 이름이 있다** — 대중이 이미 아는 작품·인물·기관·브랜드.
3. **한 문장으로 끝난다** — 배경 설명이 필요하면 탈락.

장르 무제한(미술·문학·출판·영화·드라마·뮤지컬·공연·웹툰·애니·K팝·문화재·문화정책).
우선순위: **사건성 > 인지도 > 신선도(4일 이내) > 시각 임팩트**.
가산점: "한국 최초" · 글로벌 진출 · 논란/보이콧 · 기념 주기 · 국립기관×대중브랜드.

즉시 탈락: 인터뷰·칼럼·연재(①②③), 지자체 소규모 행사(강좌·공모·체험), 폐막 결과 보도,
인사·예산 등 순수 행정, 신진작가 개인전·소규모 갤러리전·아트페어 부스, 시각 자료 전무.
단 **전국 단위 문화정책은 채택**(청년문화예술패스 급).

⚠️ **케이팝·셀럽은 접점 필수** — 컴백·신보·투어·팬미팅 그 자체는 탈락(2026-08-25 실사고: 빅뱅 투어
개막·NCT127 신보가 그대로 나갔다). 아래 중 하나가 있어야 통과: ① 국립·문화기관 콜라보
② 타 예술 장르 진출 ③ 사회적 이슈·스탠스.

> 참고: `tools/signal_scan.py`(L1 시그널)는 **로컬 전용**이다. Codex는 로컬에서 도니 돌려도 되지만
> 필수는 아니다. 실행했다면 `output/signals_latest.json`을 함께 커밋할 것.
> **GitHub Actions에는 절대 연결하지 마라** — IP가 차단돼 기존 이미지 수집까지 막힌다.

### STEP 3 — image_url 확정 (`image-rules.md` 읽고 진행)

`news_url`(디스코드 링크용 한국 기사)과 `image_url`(CI가 이미지 추출)은 **항상 분리**한다.

- ✅ 1순위: 직접 CDN 이미지 URL(`.jpg`/`.png`/`.webp`), 가로 1000px 이상 권장
- ✅ 허용: `koreaherald.com`, `koreajoongangdaily.joins.com`, `hypebeast.com`, `dezeen.com`,
  `wallpaper.com`, `vogue.com`, `architecturaldigest.com`, `wsj.com`, 공식 갤러리 영문 사이트
- ❌ 불가(CI에서 403): `*.go.kr`, `kh.or.kr`, `korea.kr`, `biz.heraldcorp.com`, `news1.kr`

운영 패턴: 한국어 기사 → `news_url`. 같은 소식의 영문 보도를 검색 → `image_url`.

⚠️ **페이지 URL을 골랐으면 반드시 직접 이미지 URL로 해상(resolve)한 뒤 쓴다.**
`news_poster.py`는 직접 이미지 URL만 받는다 — 기사/전시 페이지 URL을 주면
`PIL.UnidentifiedImageError`로 죽는다 (페이지 스캔은 CI 쪽 `discord_notify_ci.py`에만 있다).
2026-09-02 드라이런 실사고.

```bash
python -c "
from tools.article_parser import find_best_image
b, w, h = find_best_image('여기에 후보 페이지 URL', min_width=500, min_height=400)
print(w, h, b)
"
```

- 출력된 `b`(직접 CDN URL)를 **JSON의 `image_url`과 STEP 5의 `--image_url` 양쪽에 쓴다.**
  이러면 image-rules의 "1순위 = 직접 CDN URL"도 자동으로 충족된다.
- 가로 800px 미만이면 후보를 교체한다. 1000px 이상이 권장선이다.
- `find_best_image`가 예외를 던지거나 후보를 못 찾으면 그 후보는 교체 대상이다.

### STEP 4 — 헤드라인·캡션 (`headline-caption.md` 읽고 진행)

- 2줄, 각 6~11자(공백 포함). 1줄 = 고유명사(작품·인물·기관), 2줄 = 사건 동사형.
- **어절 중간 절단 절대 금지**("SDF2026영디자이" 류), 줄 끝 조사·쉼표 금지, 자극형("역대급"·"충격") 금지.
- 좋은 예: `소설 급류 / 영화화 확정`, `산호 작가 / 아이스너상 수상`, `블랙핑크 / 뮷즈 콜라보`
- 출처는 `© 원저작권자` — 신문사명이 아니라 실제 원출처. `서울시 제공`·`자료사진`·언론사명으로
  끝나면 확정으로 보지 말고 한 단계 더 추적한다.
- 계정 크레딧: `에디터 | 큐`

### STEP 5 — 이미지 생성 (2건 순차)

```bash
python tools/news_poster.py --headline1 "1줄" --headline2 "2줄" \
  --source "© 원저작권자" --image_url "확정 URL" --scale 2 \
  --output "output/news/YYYY-MM-DD_키워드_N.png"
```

`--image_url`에는 **STEP 3에서 해상한 직접 이미지 URL**을 넣는다 (페이지 URL 넣으면 크래시).

로컬에서 403으로 어두운 배경이 나와도 정상 — CI가 `image_url`로 재생성한다.
"블러 배경 적용" 로그가 보이면 더 큰 원본을 찾아 재시도(블러는 최후 수단).

### STEP 6 — 메타 JSON 저장 (`output/news/YYYY-MM-DD_키워드_N.json`)

```json
{
  "news_title": "기사 제목",
  "news_url": "한국어 기사 URL (Discord 링크용)",
  "image_url": "직접 CDN 또는 허용 도메인 URL (CI 이미지 추출용)",
  "headline1": "1줄",
  "headline2": "2줄",
  "source": "© 원저작권자",
  "caption": "캡션 #태그1 #태그2 #태그3 #태그4 #아트매거진",
  "published_at": "YYYY-MM-DD",
  "candidates": [{"title": "", "url": ""}, {"title": "", "url": ""}]
}
```

### STEP 6.5 — URL 실재 검증 (FAIL이면 커밋 금지)

**`news_url`·`image_url`은 검색에서 실제로 연 URL만 쓴다. 추측·조합 절대 금지.**
`.claude/skills/daily-news/SKILL.md`의 STEP 6.5 검증 스니펫을 실행해 **전부 OK**가 나와야 다음으로 간다.
FAIL이면 URL을 실제 기사로 교체하거나 후보 자체를 교체하고 재검증한다.

### STEP 7 — 커밋 & 푸시 (CI가 Discord 전송)

```bash
git switch -c "claude/news-$(date +%Y%m%d)" 2>/dev/null || git switch "claude/news-$(date +%Y%m%d)"
git add output/news/YYYY-MM-DD_*.png output/news/YYYY-MM-DD_*.json
git commit -m "feat(news): YYYY-MM-DD 일일 뉴스 썸네일 2건"
git push -u origin HEAD
```

- 브랜치는 **반드시 `claude/`로 시작** (CI 트리거 조건).
- `main`에 직접 커밋하지 마라.
- non-fast-forward로 거절되면 `git fetch origin && git rebase origin/main` 후 재시도.

### STEP 8 — 완료 보고 (`--output-last-message` 파일에 남는다)

```
📰 YYYY-MM-DD 발행 완료

[1] 제목 | 헤드라인: "1줄"/"2줄" | 이미지: 해상도/블러 여부
캡션: (전문)

[2] ...

❌ 제외: [제목] — 사유 (이력 중복 / 점수 미달 / 이미지 화질 미달 등)
```

---

## 4. Codex가 절대 하지 말아야 할 것

1. **`DISCORD_WEBHOOK_URL`을 코드·커밋·로그에 쓰지 마라.** GitHub Repo Secret에만 존재한다.
   로컬에서 Discord로 직접 쏘지 말고 반드시 "푸시 → CI" 경로를 쓴다.
2. **3건 이상 발행 금지.** 정확히 2건.
3. **`main` 직접 푸시 금지.**
4. **`.github/workflows/*` 수정 금지** (사람이 명시적으로 요청할 때만).
5. **`signal_scan.py`를 GitHub Actions에 연결 금지** — IP 차단.
6. **STEP 0에서 이미 발행됐으면 그 자리에서 종료.** "그래도 하나쯤 더" 금지.
7. **URL 추측·조합 금지** (STEP 6.5).

---

## 5. 실패 시 진단 순서

| 증상 | 확인 |
|---|---|
| Discord에 안 옴 | 브랜치가 `claude/*`인지 → GitHub Actions `discord-notify` 실행 로그 |
| 썸네일이 회색·어두운 배경 | `image_url`이 차단 도메인인지 (`*.go.kr`, `news1.kr` 등) |
| 하루 4건 발행됨 | Claude 클라우드 루틴이 아직 켜져 있음 → 끄기 |
| 새벽에 알림이 옴 | GitHub Actions 폴백 지연. `daily-news.yml`의 KST 16:50~19:30 컷오프 확인 |
| Codex가 그냥 종료 | `output/codex_last_run.txt` 확인 — STEP 0 스킵인지 진짜 실패인지 구분 |
| 푸시 거절 | `git fetch origin && git rebase origin/main` 후 재푸시 |

---

## 6. 윈도우 예약작업 등록 (사람이 1회)

러너 스크립트 `tools/run_daily_news_codex.ps1`을 매일 16:07에 돌린다.

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\hyein\Documents\hyein-projects\art-tool\tools\run_daily_news_codex.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 16:07
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "피아트_일일뉴스_Codex" `
  -Action $action -Trigger $trigger -Settings $set `
  -Description "p.art_mag 일일 뉴스 2건 자동 발행 (Codex)"
```

- `-StartWhenAvailable` — PC가 꺼져 있어 놓친 실행을 다음 로그온 때 보충한다.
- 테스트: `Start-ScheduledTask -TaskName "피아트_일일뉴스_Codex"` → 몇 분 뒤 `output\codex_last_run.txt` 확인.
- 끄기: `Disable-ScheduledTask -TaskName "피아트_일일뉴스_Codex"`
