<#
  加速器学习驾驶舱 · 统一入口

  run.ps1 ingest  [-Full] [-Only <相对路径>] [-NoOcr]
  run.ps1 query   "<问题>" [-Course <目录>] [-Kind slide|book|paper|doc] [-K 8] [-AllVersions] [-FullText]
  run.ps1 papers  [-DryRun | -Write]
  run.ps1 weekly  [-NoIngest]
  run.ps1 ocr     -Doc <相对路径> -Pages 5-6    （或 -Pilot）
  run.ps1 eval    [命中判据 top-N，默认 3]
  run.ps1 status
#>
param(
  [Parameter(Position = 0, Mandatory = $true)]
  [ValidateSet('ingest', 'query', 'papers', 'weekly', 'ocr', 'eval', 'status')]
  [string]$Command,

  [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'

$Tools = $PSScriptRoot

# 依次尝试：ACCKB_* 环境变量 -> Codex 自带运行时 -> 系统 PATH。换机器不用改代码。
function Resolve-Tool {
  param([string]$EnvVar, [string]$RuntimeRel, [string[]]$Commands)
  if ($EnvVar) {
    $value = [Environment]::GetEnvironmentVariable($EnvVar)
    if ($value -and (Test-Path -LiteralPath $value)) { return $value }
  }
  $roots = @()
  if ($env:ACCKB_RUNTIME) { $roots += $env:ACCKB_RUNTIME }
  $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
  $roots += (Join-Path (Split-Path -Parent $codexHome) '.cache\codex-runtimes\codex-primary-runtime\dependencies')
  foreach ($root in $roots) {
    if (-not $RuntimeRel) { continue }
    $candidate = Join-Path $root $RuntimeRel
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  foreach ($cmd in $Commands) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
  }
  return $null
}

$PY = Resolve-Tool -EnvVar 'ACCKB_PYTHON' -RuntimeRel 'python\python.exe' -Commands @('python', 'python3')
if (-not $PY) {
  throw '找不到 Python。请安装 Python 3.9+ 并加入 PATH，或设环境变量 ACCKB_PYTHON 指向解释器。'
}

if (-not $env:NODE_PATH) {
  $nodeModules = Resolve-Tool -RuntimeRel 'node\node_modules' -Commands @()
  if (-not $nodeModules) { $nodeModules = Resolve-Tool -EnvVar 'ACCKB_NODE_MODULES' -Commands @() }
  if ($nodeModules) { $env:NODE_PATH = $nodeModules }
}

$switches = @{
  ingest = @{ '-Full' = '--full'; '-Only' = '--only'; '-NoOcr' = '--no-ocr' }
  query  = @{ '-Course' = '--course'; '-Kind' = '--kind'; '-K' = '-k'; '-AllVersions' = '--all-versions'; '-FullText' = '--full-text' }
  papers = @{ '-Write' = '--write'; '-DryRun' = '--dry-run'; '-Priorities' = '--priorities' }
  weekly = @{ '-NoIngest' = '--no-ingest' }
  ocr    = @{ '-Doc' = '--doc'; '-Pages' = '--pages'; '-Pilot' = '--pilot' }
  eval   = @{}
  status = @{}
}

$script = switch ($Command) {
  'ingest' { Join-Path $Tools 'ingest.py' }
  'query'  { Join-Path $Tools 'query.py' }
  'papers' { Join-Path $Tools 'fetch_papers.py' }
  'weekly' { Join-Path $Tools 'weekly.py' }
  'ocr'    { Join-Path $Tools 'ocr_pdf.py' }
  'eval'   { Join-Path $Tools 'eval_retrieval.py' }
  'status' { Join-Path $Tools 'status.py' }
}

$map = $switches[$Command]
$items = @()
if ($null -ne $Rest) { $items = @($Rest) }
$pyArgs = @()

if ($Command -eq 'query') {
  if ($items.Count -lt 1 -or [string]::IsNullOrWhiteSpace($items[0])) {
    throw 'query 需要提供问题文本，例如：run.ps1 query "束流位置怎么测"'
  }
  $pyArgs += '--query'
  $pyArgs += $items[0]
  $items = @($items | Select-Object -Skip 1)
}

foreach ($item in $items) {
  if ($map.ContainsKey($item)) { $pyArgs += $map[$item] } else { $pyArgs += $item }
}

& $PY $script @pyArgs
exit $LASTEXITCODE
