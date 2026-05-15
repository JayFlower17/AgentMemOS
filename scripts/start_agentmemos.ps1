param(
    [ValidateSet("local", "llm")]
    [string]$Mode = "local",
    [int]$Port = 8000,
    [string]$Database = "",
    [switch]$Reload
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

if (-not $Database) {
    $Database = if ($Mode -eq "llm") { "agentmemos_llm.db" } else { "agentmemos.db" }
}

$env:AGENTMEMOS_DATABASE_URL = "sqlite:///./$Database"
$env:AGENTMEMOS_VECTOR_STORE_BACKEND = "memory"

if ($Mode -eq "llm") {
    $env:AGENTMEMOS_EXTRACTOR_BACKEND = "openai"
    $env:AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND = "openai"
    $env:AGENTMEMOS_EMBEDDING_PROVIDER = "openai"
    $env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED = "true"
    if (-not $env:AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT) {
        $env:AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT = "0.35"
    }
    if (-not $env:AGENTMEMOS_OPENAI_API_KEY) {
        throw "Missing AGENTMEMOS_OPENAI_API_KEY. Put it in .env or set it in PowerShell."
    }
    if (-not $env:AGENTMEMOS_OPENAI_BASE_URL) {
        throw "Missing AGENTMEMOS_OPENAI_BASE_URL. Put it in .env or set it in PowerShell."
    }
    if (-not $env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY) {
        throw "Missing AGENTMEMOS_OPENAI_EMBEDDING_API_KEY. Put it in .env or set it in PowerShell."
    }
    if (-not $env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL) {
        throw "Missing AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL. Put it in .env or set it in PowerShell."
    }
} else {
    $env:AGENTMEMOS_EXTRACTOR_BACKEND = "rule"
    $env:AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND = "rule"
    $env:AGENTMEMOS_EMBEDDING_PROVIDER = "hashing"
    $env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED = "false"
}

Write-Host "Starting AgentMemOS"
Write-Host "mode: $Mode"
Write-Host "database: $Database"
Write-Host "dashboard: http://127.0.0.1:$Port/"
Write-Host "api docs: http://127.0.0.1:$Port/docs"
Write-Host ""

$uvicornArgs = @("agentmemos.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

python -m uvicorn @uvicornArgs

