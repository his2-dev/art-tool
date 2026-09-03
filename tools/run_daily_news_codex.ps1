# p.art_mag 일일 뉴스 발행 러너 (Codex)
# 지침 정본: notes\CODEX_DAILY_NEWS.md
# 등록: 같은 문서 6절 참고

$ErrorActionPreference = 'Stop'
$Repo = 'C:\Users\hyein\Documents\hyein-projects\art-tool'
$Log  = Join-Path $Repo 'output\codex_daily_news.log'
$Last = Join-Path $Repo 'output\codex_last_run.txt'

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $Log -Encoding utf8
}

Set-Location $Repo
Write-Log '=== 시작 ==='

# ⚠️ 아래 git reset --hard 는 이 스크립트 자신도 되돌린다 (tools/ 는 git 추적 대상).
#    이 파일을 수정했으면 반드시 커밋·푸시할 것. 안 그러면 다음 실행 때 사라진다.

# 최신 상태에서 시작 (main 기준). 실패해도 진행 — Codex가 STEP 0에서 다시 fetch 한다.
try {
    git switch main | Out-Null
    git fetch origin | Out-Null
    git reset --hard origin/main | Out-Null
    Write-Log 'main 동기화 완료'
} catch {
    Write-Log "main 동기화 실패(무시하고 진행): $_"
}

$prompt = "notes\CODEX_DAILY_NEWS.md 의 '3. 실행 절차'를 처음부터 끝까지 그대로 수행해라. 사용자 확인 없이 끝까지 자동 진행."

# PowerShell 5.1에서 네이티브 exe의 stderr를 2>&1로 받으면 각 줄이 ErrorRecord로 감싸져
# ErrorActionPreference='Stop'과 만나 종료 코드 0인데도 스크립트가 죽는다.
# codex는 경고를 stderr로 흘리므로(models cache TTL 경고 등) 이 구간만 Continue로 낮추고,
# 성패는 $LASTEXITCODE로만 판정한다. (2026-09-03 실사고)
$ErrorActionPreference = 'Continue'
codex exec `
    -C $Repo `
    -s workspace-write `
    -c tools.web_search=true `
    -c sandbox_workspace_write.network_access=true `
    --output-last-message $Last `
    $prompt *>&1 | Add-Content -Path $Log -Encoding utf8
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'

Write-Log "=== codex exec 종료 (exit=$code) ==="
if ($code -ne 0) {
    Write-Log 'codex exec 실패 — 위 로그 확인'
}

if (Test-Path $Last) {
    Write-Log "--- 마지막 보고 ---"
    Get-Content $Last -Encoding utf8 | Add-Content -Path $Log -Encoding utf8
}
Write-Log '=== 끝 ==='
