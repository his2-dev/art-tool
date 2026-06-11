# p.art_mag 인스타그램 매거진 운영 규칙

## 기본 원칙
- 결과물은 항상 **한국어**로 작성
- 이미지 생성 완료 후 캡션은 **채팅에 바로 출력** (복붙용)
- 로고는 배경 밝기에 따라 흰색/검정색 자동 선택
- 출처 표기는 항상 `© [원저작권자]` — 신문사명이 아닌 실제 원출처 기준
- 이미지 출처 확인 순서: `원저작권자/공식 제공처 > 기관 공식 뉴스룸 > 기사 캡션 표기`
- `서울시 제공`, `자료사진`, 언론사명으로 끝나면 확정 출처로 보지 말고 한 단계 더 추적
- 계정 크레딧: `에디터 | 큐`

## 편집 방향 (큐레이션 기준)
레퍼런스 채널이 "올릴 법한" 소식만 다룬다:
`artart.today`, `cultureart4u`(널 위한 문화예술), `artinculture`(아트인컬처), `lingrongdang`(링롱댕),
`b.framemag`, `design.co.kr`, `eyesmag.com`, `careet.net`

이 채널들의 공통 감성: **"이게 왜 재밌는지" 이야기가 되는 동시대 미술 소식** — 작품/전시 뒤의 스토리,
MZ가 저장·공유하고 싶은 비주얼, 니치하지만 힙한 취향까지. 우선순위:

1. **타이밍** — 이번 주 개막·발표·이슈
2. **화제성** — SNS 반응, 셀럽 연관, 팝컬처 접점
3. **시각 임팩트** — 썸네일 한 장으로 멈춰서게 할 이미지 (실제 확보 가능해야 함)
4. **인지도** — 유명 기관/작가, 대중 접근성 높은 주제
5. **아트씬 의미** — "이게 왜 중요한가" 설명 가능한 것

**제외**: 인터뷰·칼럼·연재(①②③), 보도자료성 행사 알림(강좌·공모·체험), 폐막 결과 보도, 시각 임팩트 없는 정책·인사 소식

---

## 운영 모드

### 수동 모드 (대화 요청 시)
"게시물/뉴스 만들어줘" → **즉시 생성 금지**. 순서 준수:

1. 뉴스 후보 3건 제시 — 각 후보마다:
   - 기사 제목 / 선택 이유 / 헤드라인 2줄 초안
   - 이미지 출처 상태 (`확정 / 유력 / 미확정`) + 사용 예정 `image_url`
   - 미확정이면 생성 전 먼저 알릴 것
2. 후보 제시 전 최소 2개 출처로 교차 확인, 공식 페이지/보도자료 1개 포함
3. 사용자 선택 후 → 핵심 사실(날짜·장소·주최) 재검증 → PNG 생성 → JSON 저장 → 커밋·푸시
4. `image_url`은 아래 규칙의 허용 도메인으로 확정 후 진행

### 자동 모드 (스케줄 — 매일 12:00 KST)
사용자 확인 없이 3건 전체 자동 진행. 파이프라인: `.claude/skills/daily-news/` (daily-news 스킬)

### 폴백 자동 모드 (GitHub Actions — 매일 13:00 KST)
`.github/workflows/daily-news.yml` + `tools/daily_auto.py`.
당일 발행물(JSON)이 main에 이미 있으면 자동 스킵. RSS(검색 기반 Bing News + 언론사 피드)에서
점수 기반 큐레이션(인터뷰·칼럼·연재 자동 제외) 후 3건 발행.

---

## 파일 위치

| 종류 | 경로 |
|------|------|
| 이미지 생성 | `tools/news_poster.py` |
| 기사 파서 (curl_cffi 우회 포함) | `tools/article_parser.py` |
| 폴백 자동 셀렉터 | `tools/daily_auto.py` |
| Discord 전송 (CI용) | `tools/discord_notify_ci.py` |
| Discord 전송 (로컬용) | `tools/discord_sender.py` |
| Streamlit 웹앱 | `app.py` |
| 로고/폰트 에셋 | `tools/assets/` |
| 생성된 뉴스 이미지 | `output/news/` |
| 발행 파이프라인 스킬 | `.claude/skills/daily-news/` (SKILL.md + curation/image-rules/headline-caption) |

---

## Figma 정보

| 항목 | 값 |
|------|-----|
| 파일 키 | `HFgX7HKHYYHwjCVBgA6mYD` |
| 뉴스 썸네일 노드 | `31:631` |
| 캔버스 크기 | 1080 × 1350px |

---

## 이미지 URL 규칙 (`news_url` ≠ `image_url`)

**핵심**: `news_url`(Discord 링크용 한국 기사)과 `image_url`(CI가 이미지 추출하는 URL)은 항상 분리.
CI는 `curl_cffi` Chrome 핑거프린트로 우회하지만, IP 자체가 차단된 한국 뉴스 사이트는 실패 → 회색 배경 폴백.

**✅ `image_url` 우선순위:**
1. **직접 CDN 이미지 URL** (`.jpg`/`.png`/`.webp`) — 항상 통과, **가로 1000px 이상** 권장
2. 한국 영문 매체: `koreaherald.com`, `koreajoongangdaily.joins.com`
3. 국제 컬쳐/패션: `hypebeast.com`, `dezeen.com`, `wallpaper.com`, `vogue.com`, `architecturaldigest.com`, `wsj.com`
4. 공식 갤러리 영문: `kukjegallery.com`, `pkmgallery.com`, `lvmh.com`
5. 국내 (간헐적): `design.co.kr`, `mk.co.kr`, `chosun.com`, `joongang.co.kr`, `kmib.co.kr`

**❌ `image_url` 불가 (CI에서 403):**
- `*.go.kr`, `kh.or.kr`, `korea.kr` — 정부/공공기관 전반
- `biz.heraldcorp.com`, `news1.kr` 등 한국 주요 뉴스 사이트

> 운영 패턴: 한국어 기사 → `news_url`. 같은 소식의 영문 보도(`koreaherald.com`, `hypebeast.com` 등) 검색 → `image_url`.

### 썸네일 화질 파이프라인 (news_poster.py 자동 처리)
- CI는 og:image만이 아니라 **기사 본문 이미지까지 스캔해 가장 고해상도 이미지를 채택**
- 원본 해상도가 낮으면 출력 배율을 자동으로 낮춤 (과업스케일 방지)
- 업스케일 2.4배 초과 시 **블러 배경 처리** — 픽셀 깨짐 대신 깔끔한 무드 배경
- 블러 로그가 보이면 더 큰 원본 이미지를 찾아 재생성 권장 (블러는 최후의 수단)

---

## 헤드라인 규칙

- 2줄 각 6~11자 (공백 포함). 1줄=기관·전시명(명사형), 2줄=`개막·개관·공개·개최` 등 사실형
- **어절 중간 절단 절대 금지** ("SDF2026영디자이" 류 실패작 금지), 줄 끝 조사·쉼표 금지
- 자극형("역대급", "충격") 금지
- 좋은 예: `리움미술관 / 여성 설치미술전 개막`, `아트부산 2026 / 벡스코 개막`

---

## Discord 발행 플로우

Claude Code 환경에서 Discord 직접 호출이 차단되므로, JSON+PNG를 커밋·푸시하면 CI가 자동 전송.

```bash
python tools/news_poster.py \
    --headline1 "헤드라인 1줄" \
    --headline2 "헤드라인 2줄" \
    --source "© 출처" \
    --output "output/news/YYYY-MM-DD_키워드.png"
# --image_url 생략: 로컬은 IP 차단으로 403 → 어두운 배경 PNG 저장되면 OK
# CI가 JSON의 image_url로 최적 이미지 추출해 실제 이미지로 재생성 후 Discord 전송
```

**메타 JSON** (`output/news/YYYY-MM-DD_키워드.json`):
```json
{
  "news_title": "기사 제목",
  "news_url": "한국어 기사 URL (Discord 링크용)",
  "image_url": "직접 CDN URL 또는 영문/국제 매체 URL (CI 이미지 추출용)",
  "headline1": "헤드라인 1줄",
  "headline2": "헤드라인 2줄",
  "source": "© 원저작권자",
  "caption": "캡션 #태그1 #태그2 #태그3 #태그4 #아트매거진",
  "published_at": "YYYY-MM-DD",
  "candidates": [
    {"title": "후보1", "url": "..."},
    {"title": "후보2", "url": "..."},
    {"title": "후보3", "url": "..."}
  ]
}
```

커밋·푸시 → `.github/workflows/discord-notify.yml` 자동 트리거 → Discord 전송.
**Secret**: `DISCORD_WEBHOOK_URL` — GitHub Repo Settings에만 보관. 코드·커밋에 절대 포함 금지.

---

## Streamlit 썸네일 편집기

| 항목 | 내용 |
|------|------|
| 웹앱 | `https://art-tool-news.streamlit.app/` |
| 로컬 실행 | `streamlit run app.py` |
| GitHub | `his2-dev/art-tool` |
| Keep-alive | `.github/workflows/keep-alive.yml` — 6시간마다 헬스 핑 (실패해도 경고만) |
| Discord embed URL 변경 | `ARTMAG_APP_URL` 환경변수 (GitHub Secret) |

---

## 스케줄 자동화

| 항목 | 내용 |
|------|------|
| 태스크 ID | `daily-news-thumbnail` |
| 실행 시간 | 매일 12:00 KST |
| 동작 | 뉴스 3건 선별 → 이미지 생성 → 커밋·푸시 → Discord 전송 |
| 파이프라인 | `.claude/skills/daily-news/` (daily-news 스킬) |
| 폴백 | GitHub Actions `daily-news.yml` 13:00 KST (당일 발행 있으면 스킵) |
| 관리 | Claude Code 사이드바 → Scheduled |
