param(
    [ValidateSet("local", "llm")]
    [string]$Mode = "local",
    [int]$Port = 8018,
    [switch]$RunEval,
    [int]$LimitSamples = 1,
    [int]$LimitQuestions = 10,
    [int]$LimitEventsPerSample = 80,
    [switch]$KeepServer
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Import-DotEnv -Path (Join-Path $repoRoot ".env")

$baseUrl = "http://127.0.0.1:$Port"
$dbPath = if ($Mode -eq "llm") { "agentmemos_interview_llm.db" } else { "agentmemos_interview_local.db" }

Write-Host "AgentMemOS interview quickstart"
Write-Host "mode: $Mode"
Write-Host "base_url: $baseUrl"
Write-Host "dashboard: $baseUrl/"

$env:AGENTMEMOS_DATABASE_URL = "sqlite:///./$dbPath"
$env:AGENTMEMOS_VECTOR_STORE_BACKEND = "memory"
$env:AGENTMEMOS_WORKER_CONCURRENCY = "2"

if ($Mode -eq "llm") {
    $env:AGENTMEMOS_EXTRACTOR_BACKEND = "openai"
    $env:AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND = "openai"
    $env:AGENTMEMOS_EMBEDDING_PROVIDER = "openai"
    $env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED = "true"
    $env:AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT = "0.35"
    if (-not $env:AGENTMEMOS_OPENAI_API_KEY) {
        throw "Set AGENTMEMOS_OPENAI_API_KEY before running -Mode llm."
    }
    if (-not $env:AGENTMEMOS_OPENAI_BASE_URL) {
        $env:AGENTMEMOS_OPENAI_BASE_URL = "https://api.deepseek.com"
    }
    if (-not $env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL) {
        $env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL = "deepseek-chat"
    }
    if (-not $env:AGENTMEMOS_OPENAI_GOVERNANCE_MODEL) {
        $env:AGENTMEMOS_OPENAI_GOVERNANCE_MODEL = $env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL
    }
    if (-not $env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY) {
        throw "Set AGENTMEMOS_OPENAI_EMBEDDING_API_KEY before running -Mode llm."
    }
    if (-not $env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL) {
        throw "Set AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL before running -Mode llm."
    }
    if (-not $env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL) {
        $env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL = "text-embedding-v4"
    }
} else {
    $env:AGENTMEMOS_EXTRACTOR_BACKEND = "rule"
    $env:AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND = "rule"
    $env:AGENTMEMOS_EMBEDDING_PROVIDER = "hashing"
    $env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED = "false"
}

$server = $null
try {
    $server = Start-Process -FilePath python `
        -ArgumentList @("-m", "uvicorn", "agentmemos.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput "interview_quickstart.out.log" `
        -RedirectStandardError "interview_quickstart.err.log" `
        -PassThru

    Start-Sleep -Seconds 3
    Invoke-RestMethod "$baseUrl/health" | Out-Null

    Write-Host ""
    Write-Host "Running system demo..."
    python examples/interview_demo.py --mode $Mode --base-url $baseUrl --print-dashboard-url --wait-timeout 90

    Write-Host ""
    Write-Host "Running governance eval..."
    python evals/run_governance_eval.py --dataset evals/datasets/agentmemos_governance_gold.json --base-url $baseUrl --mode $Mode

    if ($RunEval) {
        Write-Host ""
        Write-Host "Running LoCoMo retrieval eval..."
        $evalArgs = @(
            "evals/run_retrieval_eval.py",
            "--dataset", "evals/datasets/locomo10.json",
            "--base-url", $baseUrl,
            "--limit-samples", "$LimitSamples",
            "--limit-questions", "$LimitQuestions",
            "--mode", $Mode,
            "--wait-timeout", "180"
        )
        if ($LimitEventsPerSample -gt 0) {
            $evalArgs += @("--limit-events-per-sample", "$LimitEventsPerSample")
        }
        python @evalArgs
    }

    Write-Host ""
    Write-Host "Done."
    Write-Host "Dashboard: $baseUrl/"
    Write-Host "Docs: $baseUrl/docs"
    Write-Host "Reports: evals/reports/"
} finally {
    if ($server -and -not $KeepServer) {
        Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
        Write-Host "Stopped server process $($server.Id). Use -KeepServer to keep the dashboard open."
    } elseif ($server) {
        Write-Host "Server kept running: pid $($server.Id)"
    }
}
