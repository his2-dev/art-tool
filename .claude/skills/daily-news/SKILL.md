---
name: daily-news
description: p.art_mag 일일 뉴스 썸네일 3건 자동 발행 — 뉴스 큐레이션부터 썸네일 생성, JSON 저장, 커밋·푸시, 완료 보고까지. 스케줄 태스크 또는 "뉴스 발행해줘" 요청 시 사용.
---

# p.art_mag 일일 뉴스 발행 파이프라인

오늘의 문화예술 뉴스 3건 선별 → 썸네일 3개 생성 → 커밋·푸시(CI가 Discord 전송) → 완료 보고.
**사용자 확인 단계 없음. 끝까지 혼자 진행.**

각 단계에서 지정된 보조 문서를 **그 단계 시작 전에 반드시 읽을 것**:

| 단계 | 보조 문서 |
|------|----------|
| 후보 수집·선별 | `curation.md` |
| image_url 확정 | `image-rules.md` |
| 헤드라인·캡션 | `headline-caption.md` |

---

## STEP 0 — 발행 이력 확인 (가장 먼저)

자동 발행 결과는 `claude/*` 작업 브랜치에만 쌓이고 main엔 머지되지 않는다. **main만 보면 어제
자신이 뭘 발행했는지 모른 채 같은 전시를 또 고르게 되므로**, 최근 `claude/*` 브랜치까지 함께 읽는다.

```bash
git fetch -q origin '+refs/heads/claude/*:refs/remotes/origin/claude/*' || true
python3 - <<'PY'
import json, subprocess
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=30)).isoformat()

def sh(args):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout

refs = ["origin/main"]
branches = [b.strip() for b in sh(
    ["git", "for-each-ref", "--sort=-committerdate",
     "--format=%(refname:short)", "refs/remotes/origin/claude/"]).splitlines() if b.strip()]
refs += branches[:40]   # 최근 40개 작업 브랜치까지

seen, rows = set(), []
for ref in refs:
    for f in sh(["git", "-c", "core.quotepath=false", "ls-tree", "-r",
                 "--name-only", ref, "output/news"]).splitlines():
        if not f.endswith(".json"):
            continue
        try:
            d = json.loads(sh(["git", "show", f"{ref}:{f}"]))
        except Exception:
            continue
        if str(d.get("published_at", "2000-01-01"))[:10] < cutoff:
            continue
        line = (f'{str(d.get("published_at",""))[:10]} | '
                f'{d.get("headline1","")} {d.get("headline2","")} | '
                f'{str(d.get("news_title",""))[:40]}')
        if line not in seen:
            seen.add(line)
            rows.append(line)
for r in sorted(rows):
    print(r)
PY
```

**규칙 (예외 없음)**: 목록의 작가명·전시명·기관명과 같거나 유사한 후보는 즉시 탈락.
표기 변형도 동일 대상 ("데미안 허스트" = "데이미언 허스트" = "Damien Hirst").
전시가 진행 중이어도 이미 발행했으면 재선정 금지.

## STEP 1 — 오늘 날짜 확인

```bash
python3 -c "from datetime import date; d=date.today(); print(d.isoformat(), f'{d.month}월 {d.day}일')"
```

## STEP 2 — 후보 수집·선별 → `curation.md` 읽고 진행

10건 이상 수집 → 점수 평가 → 서로 다른 카테고리 3건 확정.

## STEP 3 — image_url 확정 → `image-rules.md` 읽고 진행

3건 모두 허용 출처에서 이미지 확보 (가로 800px 이상 확인). 미달이면 후보 교체.

## STEP 4 — 헤드라인·캡션 작성 → `headline-caption.md` 읽고 진행

## STEP 5 — 이미지 생성 (3건 순차)

```bash
python tools/news_poster.py \
  --headline1 "1줄" --headline2 "2줄" \
  --source "© 원저작권자" \
  --image_url "확정한 image_url" \
  --scale 2 \
  --output "output/news/YYYY-MM-DD_키워드_N.png"
```

> 로컬에서 403으로 어두운 배경이 떠도 정상 — CI가 image_url로 재생성한다.
> "블러 배경 적용" 로그가 보이면 더 큰 원본 이미지를 찾아 재생성 시도 (블러는 최후 수단).

## STEP 6 — 메타 JSON 저장 (3건 각각)

`output/news/YYYY-MM-DD_키워드_N.json`:

```json
{
  "news_title": "기사 제목",
  "news_url": "한국어 기사 URL (Discord 링크용)",
  "image_url": "직접 CDN 또는 허용 도메인 URL (CI 이미지 추출용)",
  "headline1": "1줄", "headline2": "2줄",
  "source": "© 원저작권자",
  "caption": "캡션 #태그1 #태그2 #태그3 #태그4 #아트매거진",
  "published_at": "YYYY-MM-DD",
  "candidates": [{"title":"","url":""},{"title":"","url":""},{"title":"","url":""}]
}
```

## STEP 6.5 — URL 실재 검증 (FAIL이면 커밋 금지)

**`news_url`·`image_url`은 검색에서 실제로 연 URL만. 절대 추측·조합하지 말 것.** 아래로 검증:

```bash
python3 - <<'PY'
import json, glob, sys
from datetime import date
from tools.article_parser import http_get
bad = 0
for f in sorted(glob.glob(f"output/news/{date.today().isoformat()}_*.json")):
    d = json.load(open(f, encoding="utf-8"))
    for key in ("news_url", "image_url"):
        u = d.get(key, "")
        try: ok = http_get(u).status_code == 200
        except Exception: ok = False
        print(("OK  " if ok else "FAIL") + f" {key}: {u}")
        bad += 0 if ok else 1
sys.exit(1 if bad else 0)
PY
```

FAIL이 하나라도 나오면 그 후보의 URL을 **실제 기사**로 교체(또는 후보 자체 교체)하고 재검증. 전부 OK여야 STEP 7.

## STEP 7 — 커밋 & 푸시 (CI가 Discord 전송)

```bash
git add output/news/YYYY-MM-DD_*.png output/news/YYYY-MM-DD_*.json
git commit -m "feat(news): YYYY-MM-DD 일일 뉴스 썸네일 3건"
git push -u origin HEAD
```

## STEP 8 — 완료 보고 (채팅 출력)

```
📰 YYYY-MM-DD 발행 완료

[1] 제목 | 헤드라인: "1줄"/"2줄" | 이미지: 해상도/블러 여부
캡션: (전문)

[2] ... / [3] ...

❌ 제외: [제목] — 사유 (이력 중복 / 점수 미달 / 이미지 화질 미달 등)
```
