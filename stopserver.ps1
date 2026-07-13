# Stop Django dev servers listening on port 8000
$pids = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($procId in $pids) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine -match 'manage\.py runserver') {
        Write-Host "Stopping PID $procId : $($p.CommandLine)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
