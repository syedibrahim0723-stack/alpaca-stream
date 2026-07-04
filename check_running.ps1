Write-Output "--- cmd / gcloud / plink / python processes ---"
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'cmd|gcloud|plink|python|conhost' } | Select-Object ProcessId, Name, CommandLine | Format-List
