param(
    [int]$Port = 8021,
    [switch]$RunEval,
    [int]$LimitSamples = 1,
    [int]$LimitQuestions = 10,
    [int]$LimitEventsPerSample = 80,
    [switch]$KeepServer
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "interview_quickstart.ps1"

$argsList = @(
    "-Mode", "llm",
    "-Port", "$Port",
    "-LimitSamples", "$LimitSamples",
    "-LimitQuestions", "$LimitQuestions",
    "-LimitEventsPerSample", "$LimitEventsPerSample"
)

if ($RunEval) {
    $argsList += "-RunEval"
}

if ($KeepServer) {
    $argsList += "-KeepServer"
}

& powershell -ExecutionPolicy Bypass -File $script @argsList

