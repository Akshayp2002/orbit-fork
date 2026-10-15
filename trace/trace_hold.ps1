# Records a Bluetooth stack trace while you press-and-hold the CMF dial.
# Must run as admin (wpr needs it).
$dir = $PSScriptRoot
$etl = Join-Path $dir "hold.etl"
wpr -cancel 2>$null | Out-Null
wpr -start "$dir\BluetoothStack.wprp!BluetoothStack.Verbose" -filemode
if ($LASTEXITCODE -ne 0) { Write-Host "wpr start failed ($LASTEXITCODE)"; Read-Host "Enter to close"; exit 1 }

Write-Host ""
Write-Host "RECORDING. Press-and-hold the dial ~2s, release, wait, repeat 3 times." -ForegroundColor Green
for ($i = 25; $i -gt 0; $i--) { Write-Host -NoNewline "`r$i s left  "; Start-Sleep 1 }
Write-Host ""

wpr -stop $etl
Write-Host "Saved $etl"
Start-Sleep 3
