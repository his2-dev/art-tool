# 스케줄 태스크 지침 (v4 — 스킬 기반)

> 일일 발행 파이프라인은 `.claude/skills/daily-news/`로 이전됨.
> 규칙 수정은 그 폴더의 파일만 고치면 됨 (태스크 지침 재복붙 불필요).

| 파일 | 내용 |
|------|------|
| `.claude/skills/daily-news/SKILL.md` | 발행 파이프라인 (STEP 0~8) |
| `.claude/skills/daily-news/curation.md` | 큐레이션 기준·점수표·레퍼런스 채널 |
| `.claude/skills/daily-news/image-rules.md` | image_url 화이트리스트·화질 검증 |
| `.claude/skills/daily-news/headline-caption.md` | 헤드라인·캡션·출처 규칙 |

## 스케줄 태스크 지침 란에 넣을 내용 (이 한 단락이 전부)

```
daily-news 스킬을 실행해서 오늘의 문화예술 뉴스 3건을 발행해.
사용자 확인 없이 끝까지 자동 진행. 스킬이 안 보이면
.claude/skills/daily-news/SKILL.md 를 직접 읽고 그대로 따라.
```
