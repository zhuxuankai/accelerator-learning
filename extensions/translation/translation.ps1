param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
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
