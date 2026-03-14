$startTime = Get-Date

while ($true) {
    Clear-Host
    try {
        $p = Invoke-RestMethod -Uri http://localhost:8000/api/crawl/progress -ErrorAction Stop
    } catch {
        Write-Host "  [!] API unreachable, retrying..." -ForegroundColor Red
        Start-Sleep 10
        continue
    }

    $elapsed = (Get-Date) - $startTime
    $elapsedStr = "{0:hh\:mm\:ss}" -f $elapsed

    # Header
    Write-Host ""
    Write-Host "  =========================================" -ForegroundColor Cyan
    Write-Host "   COPYPOLY CRAWL MONITOR" -ForegroundColor Cyan
    Write-Host "  =========================================" -ForegroundColor Cyan
    Write-Host ""

    # Status
    $status = if ($p.is_running) { "RUNNING" } else { "IDLE" }
    $statusColor = if ($p.is_running) { "Green" } else { "Yellow" }
    Write-Host "  Status:      " -NoNewline; Write-Host $status -ForegroundColor $statusColor
    Write-Host "  Elapsed:     $elapsedStr"
    Write-Host ""

    # Counts
    $done = $p.complete
    $running = $p.running
    $errors = $p.errors
    $total = $p.processed
    $remaining = $total - $done - $errors

    Write-Host "  Complete:    " -NoNewline; Write-Host "$done" -ForegroundColor Green -NoNewline; Write-Host " / $total traders"
    Write-Host "  Running:     " -NoNewline; Write-Host "$running" -ForegroundColor Cyan
    Write-Host "  Errors:      " -NoNewline
    if ($errors -gt 0) { Write-Host "$errors" -ForegroundColor Red } else { Write-Host "0" -ForegroundColor Green }
    Write-Host "  Remaining:   $remaining"
    Write-Host ""

    # Data
    $storedK = [math]::Round($p.total_activities_stored / 1000, 1)
    Write-Host "  Events:      ${storedK}K stored"

    # Progress bar
    $pct = if ($total -gt 0) { [math]::Round(($done / $total) * 100, 1) } else { 0 }
    $barLen = 40
    $filled = [math]::Floor($barLen * $pct / 100)
    $empty = $barLen - $filled
    $bar = ("=" * $filled) + ("-" * $empty)
    Write-Host ""
    Write-Host "  [$bar] $pct%" -ForegroundColor Cyan

    # ETA
    if ($done -gt 0 -and $remaining -gt 0) {
        $secPerTrader = $elapsed.TotalSeconds / $done
        $etaSec = [math]::Round($secPerTrader * $remaining)
        $etaMin = [math]::Round($etaSec / 60, 1)
        Write-Host "  ETA:         ~${etaMin} min" -ForegroundColor Yellow
    }

    # Recent completions
    Write-Host ""
    Write-Host "  ----- Recent -----" -ForegroundColor DarkGray
    $recent = $p.recent | Where-Object { $_.status -eq "COMPLETE" } | Select-Object -First 5
    foreach ($r in $recent) {
        $w = $r.wallet
        $n = $r.notes
        if ($n -match "^\[OK\]") {
            Write-Host "  $w  " -NoNewline; Write-Host $n -ForegroundColor Green
        } elseif ($n -match "^\[WARN\]") {
            Write-Host "  $w  " -NoNewline; Write-Host $n -ForegroundColor Yellow
        } else {
            Write-Host "  $w  $n"
        }
    }

    # Exit check
    if (-not $p.is_running -and $done -gt 0) {
        Write-Host ""
        Write-Host "  *** CRAWL COMPLETE ***" -ForegroundColor Green
        Write-Host "  $done traders, ${storedK}K events, $errors errors"
        Write-Host ""
        break
    }

    Write-Host ""
    Write-Host "  Refreshing in 60s... (Ctrl+C to stop)" -ForegroundColor DarkGray
    Start-Sleep 60
}
