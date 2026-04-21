# p.art_mag 인스타그램 매거진 운영 규칙

## 기본
- 결과물은 항상 **한국어**로 작성
- 초안/이미지는 파일 저장 후 응답에 전문 미출력
- 로고는 배경 밝기에 따라 `p;art` 흰색/검정색 버전을 자동 선택
- 사용자가 "게시물 만들어줘"라고 하면 **바로 생성하지 말고**
   1. 뉴스 후보 3건
   2. 각 후보별 헤드라인 초안
   3. 사용할 사진 출처
   를 먼저 제시한 뒤, 사용자의 선택을 받고 진행
- 사용자가 후보를 고른 뒤에만 `png` 썸네일 생성
- `json` 메타데이터와 Figma용 수동 패키지는 사용자가 별도로 요청한 경우에만 생성
- 이미지 생성 완료 후 캡션은 **채팅에 바로 출력**해서 복붙 가능하게 제공

---

## 파일 위치

| 종류 | 경로 |
|------|------|
| 이미지 생성 스크립트 | `tools/news_poster.py` |
| 기사 파서 | `tools/article_parser.py` |
| Discord 전송 | `tools/discord_sender.py` |
| 에셋 셋업 스크립트 | `tools/setup_assets.py` |
| Streamlit 웹앱 | `app.py` |
| 로고/폰트 에셋 | `tools/assets/` |
| 생성된 뉴스 이미지 | `output/news/` |
| Codex 운영 가이드 | `notes/codex_guide.md` |

---

## Figma 정보

| 항목 | 값 |
|------|-----|
| 파일 키 | `HFgX7HKHYYHwjCVBgA6mYD` |
| 뉴스 썸네일 노드 | `31:631` (20181111) |
| 캔버스 크기 | 1080 x 1350px |

---

## 뉴스 검색 소스

| 소스 | 용도 |
|------|------|
| WebSearch: `전시 개막 오늘 2026`, `아트 뉴스 이번주` | 최신 보도 수집 |
| WebSearch: `미술관 전시 화제 인기 2026` | 화제성·트렌드 확인 |
| WebSearch: `아트페어 갤러리 오픈 서울` | 아트씬 소식 보완 |
| https://arthub.co.kr/sub06/board01_list.htm?Sub_No=2&page=1&key_type= | 전문 아트 매체 (보조 참고) |

### 후보 선별 기준

레퍼런스 채널: **b.framemag** (컬렉터·아트 인사이더, 에디터 큐레이션 톤) / **artart.today** (MZ 타겟, 76만 팔로워, 트렌딩 아트)

이 두 채널이 공통으로 다루는 콘텐츠 유형을 우선한다:

1. **타이밍 임팩트** — "지금 이 주에 봐야 하는 이유"가 명확한 것. 이번 주 개막·발표·이슈 우선
2. **화제성·유행** — SNS에서 실제 반응이 나오는 것. 트렌딩 작가·공간·이벤트. 팝컬처 접점 있으면 가점
3. **시각적 임팩트** — 썸네일 한 장으로 멈춰서게 할 수 있는 이미지가 있는 것
4. **인지도·스케일** — 국내외 유명 기관/작가, 대중 접근성 높은 주제 (무료관람, 대형 회고전 등)
5. **아트씬 의미** — 단순 행사 알림이 아니라 "이게 왜 중요한가" 설명 가능한 것 (신진작가 발굴, 아트페어 특이점, 해외 이슈의 한국 연결고리 등)

---

## `[뉴스 게시물]` 명령

1. arthub.co.kr 최신 목록 + WebSearch → 오늘의 문화예술 뉴스 검색
2. 뉴스 후보 3건 수집 (위 선별 기준 적용)
3. 각 후보별로 아래를 함께 제시
   - 기사 제목
   - 짧은 선택 이유
   - 헤드라인 2줄 초안
   - 이미지 출처
4. 사용자의 선택을 받은 뒤 1건 진행
5. 기사 내용은 최소 2개 이상 출처로 교차 확인하고, 가능하면 공식 페이지/보도자료 1개 포함
6. 뉴스 관련 이미지 URL 추출 (출처 확인)
   - 이미지 출처는 뉴스사명이 아니라 기사 내 표기된 원출처를 우선 사용
   - 기사에 명시가 없으면 공식 페이지/보도자료/원저작권자 기준으로 다시 확인 후 표기
   - 출처 표기는 `© [원출처]` 형식 사용
7. 헤드라인 2줄 확정 (각 줄 6~9자 내외)
8. `news_poster.py` 실행하여 `png` 이미지 생성
9. 인스타 캡션 작성 (뉴스 요약 + 해시태그)
10. `output/news/YYYY-MM-DD_키워드.png` 저장, 캡션은 응답에 바로 출력

```bash
python tools/news_poster.py \
    --headline1 "제목 1줄" \
    --headline2 "제목 2줄" \
    --source "© 출처" \
    --image_url "https://..." \
    --output "output/news/2026-04-11_키워드.png"
```

---

## Streamlit 웹앱 (팀원 공유용)

| 항목 | 내용 |
|------|------|
| 로컬 실행 | `streamlit run app.py` → `localhost:8501` |
| 팀원 접속 (같은 네트워크) | `http://192.168.0.6:8501` |
| GitHub 레포 | `https://github.com/his2-dev/artmag-news-tool` |
| Streamlit Cloud | 배포 시 `https://artmag-news-tool.streamlit.app` |
| 기능 | 기사 URL 자동 파싱, 수동 입력, 로고 색상 선택(자동/흰색/검정), 2배 해상도 |

### Streamlit Cloud 배포 방법
1. `share.streamlit.io` → GitHub 연결 → `his2-dev/artmag-news-tool` → `app.py` → Deploy

---

## Discord 자동 전송 (GitHub Actions 기반)

Claude Code 웹 환경에서는 Discord 직접 호출이 차단되므로, **메타 JSON + 이미지 PNG를 커밋·푸시하면 GitHub Actions가 자동 전송**하는 구조를 사용한다.

| 항목 | 내용 |
|------|------|
| 워크플로 | `.github/workflows/discord-notify.yml` |
| CI 헬퍼 | `tools/discord_notify_ci.py` |
| 직접 호출 라이브러리 | `tools/discord_sender.py` (로컬·서버용) |
| Secret | GitHub 레포 Settings → Secrets and variables → Actions → `DISCORD_WEBHOOK_URL` |
| 트리거 | `output/news/**.json` 추가/수정 push |

### 게시물 발행 플로우
1. `news_poster.py` 실행 → `output/news/YYYY-MM-DD_키워드.png` 생성
2. **같은 경로에 메타 JSON** (`.json`) 작성 — 아래 스키마
3. 두 파일을 커밋·푸시 → GitHub Actions가 Discord 채널로 전송

### 메타 JSON 스키마
```json
{
  "news_title": "기사 제목",
  "news_url": "기사 URL",
  "image_url": "기사 URL 또는 직접 이미지 URL (CI에서 og:image 자동 추출)",
  "headline1": "헤드라인 1줄",
  "headline2": "헤드라인 2줄",
  "source": "© 출처",
  "caption": "캡션 전문 (해시태그 포함)",
  "candidates": [
    {"title": "후보1 제목", "url": "..."},
    {"title": "후보2 제목", "url": "..."},
    {"title": "후보3 제목", "url": "..."}
  ]
}
```

> `image_url`은 항상 포함할 것. 기사 URL을 넣으면 CI가 og:image를 자동 추출해 배경으로 사용한다.

### 로컬·서버에서 수동 전송 (선택)
```python
from tools.discord_sender import send_news_to_discord
send_news_to_discord(
    image_path="output/news/YYYY-MM-DD.png",
    news_title="기사 제목",
    news_url="기사 URL",
    headline1="헤드라인1",
    headline2="헤드라인2",
    source="© 출처",
    caption="캡션 (해시태그 포함)",
    candidates=[{"title": "후보 제목", "url": "후보 URL"}, ...],
)
```

> 주의: Webhook URL은 `.env` 또는 환경변수 `DISCORD_WEBHOOK_URL`에만 보관. 절대 코드·커밋에 포함 금지. Windows에서 curl은 한글 깨짐 → 반드시 Python `requests` 사용.

---

## 스케줄 자동화

| 항목 | 내용 |
|------|------|
| 태스크 ID | `daily-news-thumbnail` |
| 실행 시간 | 매일 12:00 KST |
| 동작 | 뉴스 검색 → 후보 3건 선별 → 1건 대표 선택 → 이미지 생성(2배) → Discord 전송 |
| 관리 | Claude Code 사이드바 → Scheduled |

---

## 최신 추가 규칙 (참고용)

- 사용자가 "뉴스 생성해줘"라고 말한 경우도 위와 동일하게 처리
- 후보 3건을 제시할 때는 각 후보마다 `기사 제목 / 선택 이유 / 헤드라인 2줄 초안 / 사용할 사진 소재 / 실제 이미지 출처`를 함께 제시
- 후보를 제시하기 전, 기사 내용과 핵심 사실은 최소 2개 이상 출처로 교차 확인하고 가능하면 공식 페이지/보도자료 1개 포함
- 사용자가 후보를 고른 뒤에도 최종 생성 전 핵심 사실, 날짜, 장소, 주최/주관 정보를 한 번 더 검증
- 이미지 출처는 신문사명이 아니라 기사 내 표기된 실제 원출처를 우선 사용
- 기사에 이미지 원출처가 없으면 공식 페이지, 보도자료, 원저작권자 기준으로 다시 확인 후 표기
- 출처 표기는 항상 `© [원출처]` 형식 사용
- 계정 기본 크레딧은 `에디터 | 큐`
- 이미지 출처는 `원저작권자/공식 제공처 > 참여 기관 공식 뉴스룸 > 지자체/공공기관 공식 채널 > 기사 캡션 표기` 순서로 확인
- `서울시 제공`, `자료사진`, 언론사명 표기로 끝나면 확정 출처로 보지 말고 한 단계 더 추적
- 후보 단계에서 이미지 출처 상태를 `확정 / 유력 / 미확정` 중 하나로 내부 판단하고, 미확정이면 생성 전에 먼저 알릴 것
- 헤드라인은 자극형보다 정보형 톤을 우선하고, 1줄은 기관/장소/전시명, 2줄은 `개관/개막/공개/개최` 같은 사실형 표현을 우선 사용할 것
