# Finds the newest SMS Backup & Restore file on a USB-connected Android phone (File transfer mode)
# and copies it to %USERPROFILE%\.msgorg\incoming. Read-only on the phone. Prints the copied file path, or a reason.
$ErrorActionPreference = 'SilentlyContinue'
$dest = Join-Path $env:USERPROFILE '.msgorg\incoming'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$shell = New-Object -ComObject Shell.Application
$thisPC = $shell.NameSpace(17)
$devices = @($thisPC.Items() | Where-Object { $_.IsFolder -and $_.Path -notmatch '^[A-Za-z]:\\' })
if ($devices.Count -eq 0) { Write-Output "NOPHONE"; exit 0 }
$candidates = New-Object System.Collections.ArrayList
function Find-Backups($folder, $depth) {
  if ($depth -gt 3 -or $folder -eq $null) { return }
  foreach ($it in @($folder.Items())) {
    if (-not $it.IsFolder) { continue }
    if ($it.Name -eq 'SMSBackupRestore') {
      foreach ($f in @($it.GetFolder.Items())) {
        if (-not $f.IsFolder -and $f.Name -like 'sms-*') { [void]$candidates.Add($f) }
      }
    } elseif ($depth -lt 1 -or $it.Name -match 'Phone|Internal|storage|Card|SD|Download|Documents') {
      Find-Backups $it.GetFolder ($depth + 1)
    }
  }
}
foreach ($d in $devices) { Find-Backups $d.GetFolder 0 }
if ($candidates.Count -eq 0) { Write-Output "NOBACKUP"; exit 0 }
$newest = $candidates | Sort-Object { $_.Name } -Descending | Select-Object -First 1
$name = $newest.Name; if ($name -notlike '*.xml') { $name = "$name.xml" }
$target = Join-Path $dest $name
if (Test-Path $target) { Write-Output $target; exit 0 }   # already copied earlier
$shell.NameSpace($dest).CopyHere($newest, 4 + 16)
$last = -1
for ($i = 0; $i -lt 600; $i++) {             # wait up to ~5 minutes for the copy to finish
  Start-Sleep -Milliseconds 500
  $f = Get-ChildItem $dest -Filter ($newest.Name + '*') | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($f -and $f.Length -gt 0 -and $f.Length -eq $last) {
    if ($f.Name -notlike '*.xml') { Rename-Item $f.FullName "$($f.Name).xml"; $f = Get-Item "$($f.FullName).xml" }
    Write-Output $f.FullName; exit 0
  }
  if ($f) { $last = $f.Length }
}
Write-Output "COPYFAILED"
