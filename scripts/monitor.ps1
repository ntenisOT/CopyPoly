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
    $errors = $p.errors
    $total = $p.total_traders
    $remaining = $total - $done - $errors

    Write-Host "  Complete:    " -NoNewline; Write-Host "$done" -ForegroundColor Green -NoNewline; Write-Host " / $total traders"
    $workers = if ($p.max_workers) { $p.max_workers } else { $p.running }
    Write-Host "  Workers:     " -NoNewline; Write-Host "$workers concurrent" -ForegroundColor Cyan
    Write-Host "  Errors:      " -NoNewline
    if ($errors -gt 0) { Write-Host "$errors" -ForegroundColor Red } else { Write-Host "0" -ForegroundColor Green }
    Write-Host "  Pending:     $remaining"
    Write-Host ""

    # Data
    $crawledK = [math]::Round($p.total_activities_crawled / 1000, 1)
    $storedK = [math]::Round($p.total_activities_stored / 1000, 1)
    $dbSizeMB = [math]::Round($p.total_activities_stored * 1.3 / 1024, 1)  # ~1.3KB per event
    $okCount = $p.ok
    $warnCount = $p.warn
    Write-Host "  Crawled:     ${crawledK}K events | ${storedK}K in DB (~${dbSizeMB} MB)"
    Write-Host "  Quality:     " -NoNewline; Write-Host "${okCount} OK" -ForegroundColor Green -NoNewline; Write-Host " | " -NoNewline; Write-Host "${warnCount} WARN" -ForegroundColor Yellow

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
    Write-Host "  ----- Recent Completions -----" -ForegroundColor DarkGray
    $recent = $p.recent | Select-Object -First 5
    foreach ($r in $recent) {
        $name = $r.trader
        $evts = $r.events
        $n = $r.notes
        if ($r.status -eq "OK") {
            Write-Host "  $name " -NoNewline; Write-Host "($evts events) $n" -ForegroundColor Green
        } else {
            Write-Host "  $name " -NoNewline; Write-Host "($evts events) $n" -ForegroundColor Yellow
        }
    }
    if (-not $recent) {
        Write-Host "  (waiting for first completions...)" -ForegroundColor DarkGray
    }

    # Exit check
    if (-not $p.is_running -and $done -gt 0) {
        Write-Host ""
        Write-Host "  *** CRAWL COMPLETE ***" -ForegroundColor Green
        Write-Host "  $done traders, ${crawledK}K events, $errors errors"
        Write-Host ""
        break
    }

    Write-Host ""
    Write-Host "  Refreshing in 10s... (Ctrl+C to stop)" -ForegroundColor DarkGray
    Start-Sleep 10
}
