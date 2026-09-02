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

try {
    codex exec `
        -C $Repo `
        -s workspace-write `
        -c tools.web_search=true `
        -c sandbox_workspace_write.network_access=true `
        --output-last-message $Last `
        $prompt 2>&1 | Add-Content -Path $Log -Encoding utf8
    Write-Log '=== codex exec 종료 ==='
} catch {
    Write-Log "codex exec 실패: $_"
    exit 1
}

if (Test-Path $Last) {
    Write-Log "--- 마지막 보고 ---"
    Get-Content $Last -Encoding utf8 | Add-Content -Path $Log -Encoding utf8
}
Write-Log '=== 끝 ==='
