Write-Output "--- processes matching main.py / uvicorn / alpaca-stream ---"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'main.py|uvicorn|alpaca-stream' } | Select-Object ProcessId, Name, CommandLine | Format-List

Write-Output "--- listening ports ---"
Get-NetTCPConnection -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess | Sort-Object LocalPort | Format-Table -AutoSize
