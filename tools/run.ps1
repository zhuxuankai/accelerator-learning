<#
  加速器学习驾驶舱 v2

  run.ps1 doctor
  run.ps1 index   [-Full] [-Only <相对路径>] [-MockEmbedding]
  run.ps1 query   "<问题>" [-Course <目录>] [-Kind slide|book|paper|doc] [-K 8] [-AllVersions] [-Mode hybrid]
  run.ps1 eval    [-Suite demo|local] [-Split dev|heldout] [-Baseline lexical|vector|hybrid]
  run.ps1 weekly  [-NoIndex] [-SkipEval]
  run.ps1 progress list|suggest|confirm|reject|import-legacy ...
  run.ps1 reading  list|confirm ...
  run.ps1 papers  [-DryRun|-Write]
  run.ps1 status
#>
param(
  [Parameter(Position = 0, Mandatory = $true)]
  [ValidateSet('doctor', 'index', 'query', 'eval', 'weekly', 'progress', 'reading', 'papers', 'status')]
  [string]$Command,

  [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

$Root = Split-Path -Parent $PSScriptRoot

function Find-Python {
  if ($env:ACCKB_PYTHON -and (Test-Path -LiteralPath $env:ACCKB_PYTHON)) {
    return $env:ACCKB_PYTHON
  }
  $localVenv = Join-Path $Root '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $localVenv) { return $localVenv }
  foreach ($name in @('python', 'python3')) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
  }
  $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
  $runtime = Join-Path (Split-Path -Parent $codexHome) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
  if (Test-Path -LiteralPath $runtime) { return $runtime }
  throw '找不到 Python 3.10+。请创建 .venv、加入 PATH，或设置 ACCKB_PYTHON。'
}

$switches = @{
  index    = @{ '-Full' = '--full'; '-Only' = '--only'; '-MockEmbedding' = '--mock-embedding' }
  query    = @{ '-Course' = '--course'; '-Kind' = '--kind'; '-K' = '-k'; '-AllVersions' = '--all-versions'; '-Mode' = '--mode'; '-MockEmbedding' = '--mock-embedding' }
  eval     = @{ '-Suite' = '--suite'; '-Split' = '--split'; '-Baseline' = '--baseline'; '-MockEmbedding' = '--mock-embedding' }
  weekly   = @{ '-NoIndex' = '--no-index'; '-SkipEval' = '--skip-eval'; '-MockEmbedding' = '--mock-embedding' }
  progress = @{ '-DryRun' = '--dry-run'; '-Accept' = '--accept' }
  papers   = @{ '-DryRun' = '--dry-run'; '-Write' = '--write' }
}

$items = @()
if ($null -ne $Rest) { $items = @($Rest) }
$pyArgs = @('-m', 'acc_cockpit.cli', $Command)

if ($Command -eq 'query') {
  if ($items.Count -lt 1 -or [string]::IsNullOrWhiteSpace($items[0])) {
    throw 'query 需要问题文本，例如：run.ps1 query "束流位置怎么测"'
  }
  $pyArgs += $items[0]
  $items = @($items | Select-Object -Skip 1)
}

$map = $switches[$Command]
if ($null -ne $map) {
  foreach ($item in $items) {
    if ($map.ContainsKey($item)) { $pyArgs += $map[$item] } else { $pyArgs += $item }
  }
} else {
  $pyArgs += $items
}

$python = Find-Python
Push-Location $Root
try {
  & $python @pyArgs
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
