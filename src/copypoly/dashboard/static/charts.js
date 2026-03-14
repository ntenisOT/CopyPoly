/* ============================================================
   CopyPoly — TradingView Lightweight Charts Integration
   ============================================================ */

let equityChart = null;
let drawdownChart = null;
let equitySeries = null;
let drawdownSeries = null;

const CHART_COLORS = {
    bg: '#0a0e17',
    grid: '#1e293b',
    text: '#64748b',
    crosshair: '#475569',
    equity: '#6366f1',
    equityTop: 'rgba(99, 102, 241, 0.28)',
    equityBottom: 'rgba(99, 102, 241, 0.02)',
    drawdown: '#ef4444',
    drawdownTop: 'rgba(239, 68, 68, 0.02)',
    drawdownBottom: 'rgba(239, 68, 68, 0.20)',
};

function createChartOptions(containerId) {
    return {
        layout: {
            background: { color: CHART_COLORS.bg },
            textColor: CHART_COLORS.text,
            fontFamily: "'Inter', sans-serif",
            fontSize: 12,
        },
        grid: {
            vertLines: { color: CHART_COLORS.grid },
            horzLines: { color: CHART_COLORS.grid },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: { color: CHART_COLORS.crosshair, width: 1, style: 2 },
            horzLine: { color: CHART_COLORS.crosshair, width: 1, style: 2 },
        },
        rightPriceScale: {
            borderColor: CHART_COLORS.grid,
            scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
            borderColor: CHART_COLORS.grid,
            timeVisible: false,
        },
        handleScroll: true,
        handleScale: true,
    };
}

function initCharts() {
    const equityEl = document.getElementById('equity-chart');
    const drawdownEl = document.getElementById('drawdown-chart');

    if (!equityEl || !drawdownEl) return;

    // Clear existing
    equityEl.innerHTML = '';
    drawdownEl.innerHTML = '';

    // Equity chart
    equityChart = LightweightCharts.createChart(equityEl, createChartOptions('equity-chart'));
    equitySeries = equityChart.addAreaSeries({
        lineColor: CHART_COLORS.equity,
        topColor: CHART_COLORS.equityTop,
        bottomColor: CHART_COLORS.equityBottom,
        lineWidth: 2,
        priceFormat: { type: 'custom', formatter: (p) => '$' + p.toFixed(0) },
    });

    // Drawdown chart
    drawdownChart = LightweightCharts.createChart(drawdownEl, createChartOptions('drawdown-chart'));
    drawdownSeries = drawdownChart.addAreaSeries({
        lineColor: CHART_COLORS.drawdown,
        topColor: CHART_COLORS.drawdownTop,
        bottomColor: CHART_COLORS.drawdownBottom,
        lineWidth: 2,
        priceFormat: { type: 'custom', formatter: (p) => p.toFixed(1) + '%' },
        invertFilledArea: true,
    });

    // Sync time scales
    equityChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (range) drawdownChart.timeScale().setVisibleLogicalRange(range);
    });
    drawdownChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (range) equityChart.timeScale().setVisibleLogicalRange(range);
    });

    // Resize handler
    const resizeObserver = new ResizeObserver(() => {
        equityChart.applyOptions({ width: equityEl.clientWidth, height: equityEl.clientHeight });
        drawdownChart.applyOptions({ width: drawdownEl.clientWidth, height: drawdownEl.clientHeight });
    });
    resizeObserver.observe(equityEl);
    resizeObserver.observe(drawdownEl);
}

async function loadPerformance() {
    const days = document.getElementById('perf-period')?.value || 90;

    try {
        const data = await apiFetch(`/performance?days=${days}`);

        // Init charts if needed
        if (!equityChart) initCharts();

        // Set data
        equitySeries.setData(data.equity);
        drawdownSeries.setData(data.drawdown);

        // Add trade markers to equity chart
        if (data.trades && data.trades.length > 0) {
            const markers = data.trades.map(t => ({
                time: t.time,
                position: t.position,
                color: t.color,
                shape: t.shape,
                text: t.text,
            }));
            equitySeries.setMarkers(markers);
        }

        // Fit content
        equityChart.timeScale().fitContent();
        drawdownChart.timeScale().fitContent();

        // Update summary stats
        const s = data.summary;
        document.getElementById('perf-value').textContent = '$' + formatNumber(s.current_value);
        document.getElementById('perf-value').className = 'stat-value';

        const pnlEl = document.getElementById('perf-pnl');
        pnlEl.textContent = (s.total_pnl >= 0 ? '+$' : '-$') + formatNumber(Math.abs(s.total_pnl));
        pnlEl.className = `stat-value ${s.total_pnl >= 0 ? 'cell-positive' : 'cell-negative'}`;

        const roiEl = document.getElementById('perf-roi');
        roiEl.textContent = (s.roi_pct >= 0 ? '+' : '') + s.roi_pct.toFixed(1) + '%';
        roiEl.className = `stat-value ${s.roi_pct >= 0 ? 'cell-positive' : 'cell-negative'}`;

        document.getElementById('perf-winrate').textContent = (s.win_rate * 100).toFixed(1) + '%';
        document.getElementById('perf-trades').textContent = s.total_trades;

        const ddEl = document.getElementById('perf-dd');
        ddEl.textContent = s.max_drawdown_pct.toFixed(1) + '%';
        ddEl.className = 'stat-value cell-negative';

        // Simulation badge
        const badge = document.getElementById('perf-sim-badge');
        if (s.is_simulated) {
            badge.textContent = '⚠ SIMULATED DATA';
            badge.className = 'perf-badge simulated';
        } else {
            badge.textContent = '● LIVE DATA';
            badge.className = 'perf-badge live-data';
        }

        // Trades table
        renderTradesTable(data.trades);
    } catch (err) {
        console.error('Failed to load performance', err);
    }
}

function renderTradesTable(trades) {
    const tbody = document.getElementById('perf-trades-tbody');
    if (!tbody) return;

    const sorted = [...trades].reverse().slice(0, 50);
    tbody.innerHTML = sorted.map(t => {
        const isBuy = t.shape === 'arrowUp';
        return `
        <tr>
            <td class="cell-neutral">${t.time}</td>
            <td class="cell-name">${t.market || '—'}</td>
            <td><span class="badge ${isBuy ? 'badge-add' : 'badge-close'}">${isBuy ? 'BUY' : 'SELL'}</span></td>
            <td>$${formatNumber(t.size, 2)}</td>
            <td class="${t.pnl >= 0 ? 'cell-positive' : 'cell-negative'}">${t.pnl >= 0 ? '+' : ''}$${formatNumber(Math.abs(t.pnl), 2)}</td>
        </tr>`;
    }).join('');
}
