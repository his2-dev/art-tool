## 2026-09-04 / codex
- 한 일: Windows 예약 작업의 첫 실발행을 끝까지 검증했다. 16:07 시작, 16:56 종료(exit 0), `claude/news-20260904` 푸시, Discord Notify 성공 및 2건 전송을 확인했다. 첫 CI가 PowerShell 5.1 JSON BOM 때문에 실패한 문제를 재발 방지하도록 `discord_notify_ci.py`를 `utf-8-sig`로 보강하고, daily-news 지침 두 곳에 무BOM 저장 규칙을 추가했다. 예약 등록 예시에 배터리 허용 옵션도 반영했다.
- 지금 상태(빌드/테스트 통과 여부): BOM 포함 JSON 파싱 테스트 통과. Python 소스 `compile()` 구문 검사 및 `git diff --check` 통과. 예약 작업은 Ready/Enabled, 다음 실행 2026-09-05 16:07 KST.
- 다음에 할 일: 다음 예약 실행에서 첫 푸시부터 Discord Notify가 한 번에 성공하는지 확인한다. 필요하면 49분 실행시간과 303k 토큰 사용량을 줄이도록 큐레이션 절차를 최적화한다.
- 주의점(함정, 건드리면 안 되는 것): 오늘 첫 푸시 `73c84e7`은 BOM 때문에 전송 전에 실패했고, 수정 푸시 `cb47e1b`에서 2건이 각각 한 번씩 전송됐다. 기존 미추적 `(1)` 파일들은 사용자 소유이므로 건드리지 않았다. 자동 발행 브랜치는 Discord 트리거 때문에 계속 `claude/*`를 사용해야 한다.

## 2026-09-04 / codex — 웹 클라우드 전환
- 한 일: ChatGPT Work 웹에서 `피아트 일일 뉴스` 예약을 생성했다. 매일 16:07 KST, 첫 실행 2026-09-05 16:07, 즉시 실행 없음, GitHub `his2-dev/art-tool`의 main을 읽어 `claude/news-YYYYMMDD`로 정확히 2건을 푸시하도록 설정했다.
- 지금 상태(빌드/테스트 통과 여부): 웹 예약 상세 화면에서 활성 상태와 프롬프트를 확인했다. 기존 Windows 작업 `피아트_일일뉴스_Codex`는 Disabled/LastResult 0으로 전환했다. GitHub Actions 폴백은 유지된다.
- 다음에 할 일: 2026-09-05 첫 웹 실행에서 GitHub 브랜치 푸시와 Discord 전송까지 확인한다.
- 주의점(함정, 건드리면 안 되는 것): 웹 예약과 Windows 예약 또는 Claude 루틴을 동시에 켜면 중복 발행된다. 로컬 Windows 작업은 웹 예약 장애 시에만 다시 활성화한다. 웹 예약은 추가 API 키 없이 ChatGPT Work의 GitHub 플러그인을 사용한다.
