param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')

if ($Rest.Count -ge 2 -and $Rest[0] -eq '-RenderCheck') {
  $target = $Rest[1]
  $Node = if ($env:ACCKB_NODE) {
    $env:ACCKB_NODE
  } elseif (Test-Path (Join-Path $Root 'node\node.exe')) {
    Join-Path $Root 'node\node.exe'
  } else {
    (Get-Command node -ErrorAction Stop).Source
  }
  $moduleRoots = @()
  if ($env:NODE_PATH) { $moduleRoots += $env:NODE_PATH.Split(';') }
  if (Test-Path (Join-Path $Root 'node_modules')) {
    $moduleRoots += (Join-Path $Root 'node_modules')
  }
  $vscodeModules = Get-ChildItem -Path (Join-Path $env:USERPROFILE '.vscode\extensions\goessner.mdmath-*\node_modules') -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($vscodeModules) { $moduleRoots += $vscodeModules.FullName }
  if (-not $moduleRoots.Count) {
    throw '找不到 Markdown+Math 依赖。请在项目根目录执行 npm install。'
  }
  $env:NODE_PATH = ($moduleRoots -join ';')
  & $Node (Join-Path $PSScriptRoot 'render_check.cjs') $target
  exit $LASTEXITCODE
}

$Python = if ($env:ACCKB_PYTHON) {
  $env:ACCKB_PYTHON
} elseif (Test-Path (Join-Path $Root '.venv\Scripts\python.exe')) {
  Join-Path $Root '.venv\Scripts\python.exe'
} else {
  (Get-Command python -ErrorAction Stop).Source
}

$map = @{
  '-List' = '--list'
  '-Status' = '--status'
  '-Audit' = '--audit'
  '-Prepare' = '--prepare'
  '-RenderCheck' = '--render-check'
}
$argsOut = @()
foreach ($item in @($Rest)) {
  if ($map.ContainsKey($item)) { $argsOut += $map[$item] } else { $argsOut += $item }
}

Push-Location $Root
try {
  & $Python (Join-Path $PSScriptRoot 'translation.py') @argsOut
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
