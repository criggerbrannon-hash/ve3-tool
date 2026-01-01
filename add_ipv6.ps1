# Add IPv6 addresses to Windows
# Chạy PowerShell với quyền Administrator
# Right-click PowerShell -> Run as Administrator

# Tên adapter (xem trong ipconfig, thường là "Ethernet" hoặc "Wi-Fi")
$adapter = "Ethernet"

# Prefix của bạn
$prefix = "2001:ee0:b004:1f06"

# Add các IPv6 từ ::8 đến ::20
8..20 | ForEach-Object {
    $ipv6 = "${prefix}::$_"
    Write-Host "Adding $ipv6..." -NoNewline
    try {
        netsh interface ipv6 add address $adapter $ipv6 | Out-Null
        Write-Host " OK" -ForegroundColor Green
    } catch {
        Write-Host " Already exists or failed" -ForegroundColor Yellow
    }
}

Write-Host "`nDone! Checking IPv6 addresses:"
netsh interface ipv6 show address $adapter | Select-String "2001:ee0"

Write-Host "`nNow run: python test_ipv6_simple.py"
