$outFile = "diagnostic_output.txt"
Set-Content -Path $outFile -Value "---AGGREGATED---"
$agg = & curl.exe -i 'http://localhost:8080/api/StockDiario?sku=C0184&year=2016&month=10&page=1&pageSize=50' 2>&1
Add-Content -Path $outFile -Value $agg
Add-Content -Path $outFile -Value ""
Add-Content -Path $outFile -Value "---RAW---"
$raw = & curl.exe -i 'http://localhost:8080/api/StockDiario/raw?sku=C0184&year=2016&month=10&page=1&pageSize=50' 2>&1
Add-Content -Path $outFile -Value $raw
Add-Content -Path $outFile -Value ""
Add-Content -Path $outFile -Value "---SWAGGER---"
$sw = & curl.exe -sS 'http://localhost:8080/swagger/v1/swagger.json' 2>&1
Add-Content -Path $outFile -Value $sw
Write-Output "WROTE: $outFile"