# PowerShell script to add IPv6 addresses to Windows
# Run as Administrator: powershell -ExecutionPolicy Bypass -File add_ipv6_windows.ps1

$adapter = "Ethernet"

$ips = @(
    "2001:ee0:b004:1f00::2",
    "2001:ee0:b004:1f01::2",
    "2001:ee0:b004:1f02::3",
    "2001:ee0:b004:1f03::4",
    "2001:ee0:b004:1f04::5",
    "2001:ee0:b004:1f05::6",
    "2001:ee0:b004:1f06::7",
    "2001:ee0:b004:1f07::8",
    "2001:ee0:b004:1f08::9",
    "2001:ee0:b004:1f09::10",
    "2001:ee0:b004:1f0A::11",
    "2001:ee0:b004:1f0B::12",
    "2001:ee0:b004:1f0C::13",
    "2001:ee0:b004:1f0D::14",
    "2001:ee0:b004:1f0E::15",
    "2001:ee0:b004:1f10::16",
    "2001:ee0:b004:1f11::17",
    "2001:ee0:b004:1f12::18",
    "2001:ee0:b004:1f13::19",
    "2001:ee0:b004:1f14::20",
    "2001:ee0:b004:1f15::21",
    "2001:ee0:b004:1f16::22",
    "2001:ee0:b004:1f17::23",
    "2001:ee0:b004:1f18::24",
    "2001:ee0:b004:1f19::25",
    "2001:ee0:b004:1f1A::26",
    "2001:ee0:b004:1f1B::27",
    "2001:ee0:b004:1f1C::28",
    "2001:ee0:b004:1f1D::29",
    "2001:ee0:b004:1f1E::30",
    "2001:ee0:b004:1f1F::31",
    "2001:ee0:b004:1f20::32",
    "2001:ee0:b004:1f21::33",
    "2001:ee0:b004:1f22::34",
    "2001:ee0:b004:1f23::35",
    "2001:ee0:b004:1f24::36",
    "2001:ee0:b004:1f25::37",
    "2001:ee0:b004:1f26::38",
    "2001:ee0:b004:1f27::39",
    "2001:ee0:b004:1f28::40",
    "2001:ee0:b004:1f29::41",
    "2001:ee0:b004:1f2A::42",
    "2001:ee0:b004:1f2B::43",
    "2001:ee0:b004:1f2C::44",
    "2001:ee0:b004:1f2D::45",
    "2001:ee0:b004:1f2E::46",
    "2001:ee0:b004:1f2F::47",
    "2001:ee0:b004:1f30::48",
    "2001:ee0:b004:1f31::49",
    "2001:ee0:b004:1f32::50",
    "2001:ee0:b004:1f33::51",
    "2001:ee0:b004:1f34::52",
    "2001:ee0:b004:1f35::53",
    "2001:ee0:b004:1f36::54",
    "2001:ee0:b004:1f37::55",
    "2001:ee0:b004:1f38::56",
    "2001:ee0:b004:1f39::57",
    "2001:ee0:b004:1f3A::58",
    "2001:ee0:b004:1f3B::59",
    "2001:ee0:b004:1f3C::60",
    "2001:ee0:b004:1f3D::61",
    "2001:ee0:b004:1f3E::62",
    "2001:ee0:b004:1f3F::63",
    "2001:ee0:b004:1f40::64",
    "2001:ee0:b004:1f41::65",
    "2001:ee0:b004:1f42::66",
    "2001:ee0:b004:1f43::67",
    "2001:ee0:b004:1f44::68",
    "2001:ee0:b004:1f45::69",
    "2001:ee0:b004:1f46::70",
    "2001:ee0:b004:1f47::71",
    "2001:ee0:b004:1f48::72",
    "2001:ee0:b004:1f49::73",
    "2001:ee0:b004:1f4A::74",
    "2001:ee0:b004:1f4B::75",
    "2001:ee0:b004:1f4C::76",
    "2001:ee0:b004:1f4D::77",
    "2001:ee0:b004:1f4E::78",
    "2001:ee0:b004:1f4F::79",
    "2001:ee0:b004:1f50::80",
    "2001:ee0:b004:1f51::81",
    "2001:ee0:b004:1f52::82",
    "2001:ee0:b004:1f53::83",
    "2001:ee0:b004:1f54::84",
    "2001:ee0:b004:1f55::85",
    "2001:ee0:b004:1f56::86",
    "2001:ee0:b004:1f57::87",
    "2001:ee0:b004:1f58::88",
    "2001:ee0:b004:1f59::89",
    "2001:ee0:b004:1f5A::90",
    "2001:ee0:b004:1f5B::91",
    "2001:ee0:b004:1f5C::92",
    "2001:ee0:b004:1f5D::93",
    "2001:ee0:b004:1f5E::94",
    "2001:ee0:b004:1f5F::95",
    "2001:ee0:b004:1f60::96",
    "2001:ee0:b004:1f61::97",
    "2001:ee0:b004:1f62::98",
    "2001:ee0:b004:1f63::99",
    "2001:ee0:b004:1f64::100"
)

Write-Host "Adding $($ips.Count) IPv6 addresses to $adapter..." -ForegroundColor Cyan
Write-Host ""

$added = 0
$failed = 0

foreach ($ip in $ips) {
    try {
        New-NetIPAddress -InterfaceAlias $adapter -IPAddress $ip -PrefixLength 64 -ErrorAction Stop | Out-Null
        Write-Host "[OK] $ip" -ForegroundColor Green
        $added++
    } catch {
        Write-Host "[SKIP] $ip (already exists or error)" -ForegroundColor Yellow
        $failed++
    }
}

Write-Host ""
Write-Host "Done! Added: $added, Skipped: $failed" -ForegroundColor Cyan
Write-Host ""
Write-Host "Checking preferred addresses..." -ForegroundColor Cyan

$preferred = Get-NetIPAddress -InterfaceAlias $adapter -AddressFamily IPv6 |
    Where-Object { $_.AddressState -eq "Preferred" -and $_.IPAddress -like "2001:ee0:*" }

Write-Host ""
Write-Host "Working IPv6 addresses ($($preferred.Count) total):" -ForegroundColor Green
$preferred | ForEach-Object { Write-Host "  $($_.IPAddress)" }
