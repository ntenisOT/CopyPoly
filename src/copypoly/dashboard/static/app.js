/* ============================================================
   CopyPoly Dashboard — Frontend Logic
   ============================================================ */

const API = '/api';

// ============================================================
// Navigation
// ============================================================
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const page = link.dataset.page;
        navigateTo(page);
    });
});

function navigateTo(page) {
    // Update nav
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`[data-page="${page}"]`)?.classList.add('active');

    // Update pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`)?.classList.add('active');

    // Load data for page
    switch (page) {
        case 'overview': loadOverview(); break;
        case 'traders': loadTraders(); break;
        case 'positions': loadPositions(); break;
        case 'signals': loadSignals(); break;
        case 'performance': loadPerformance(); break;
        case 'config': loadConfig(); break;
        case 'crawl-runs': loadCrawlRuns(); break;
    }
}

// ============================================================
// API Helpers
// ============================================================
async function apiFetch(path, options = {}) {
    try {
        const resp = await fetch(`${API}${path}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (err) {
        console.error(`API error: ${path}`, err);
        showToast(`API error: ${err.message}`, 'error');
        throw err;
    }
}

// ============================================================
// Overview Page
// ============================================================
async function loadOverview() {
    try {
        const data = await apiFetch('/overview');
        document.getElementById('stat-traders').textContent = data.total_traders;
        document.getElementById('stat-watched').textContent = data.watched_traders;
        document.getElementById('stat-positions').textContent = formatNumber(data.open_positions);
        document.getElementById('stat-signals').textContent = data.total_signals;
        document.getElementById('stat-orders').textContent = data.paper_orders;

        const mode = typeof data.trading_mode === 'string'
            ? data.trading_mode.replace(/"/g, '')
            : 'paper';
        document.getElementById('stat-mode').textContent = mode.toUpperCase();

        const modeBadge = document.getElementById('trading-mode');
        modeBadge.textContent = mode.toUpperCase();
        modeBadge.className = `mode-badge${mode === 'live' ? ' live' : ''}`;

        // Load watched traders table
        const traders = await apiFetch('/traders?watched_only=true');
        renderWatchedTable(traders);
    } catch (err) {
        console.error('Failed to load overview', err);
    }
}

function renderWatchedTable(traders) {
    const tbody = document.getElementById('watched-tbody');
    tbody.innerHTML = traders.map((t, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="cell-name">${t.username || t.wallet.slice(0, 12) + '...'}</td>
            <td class="cell-highlight">${t.composite_score.toFixed(4)}</td>
            <td class="${t.best_pnl_all_time >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_all_time)}</td>
            <td class="${t.best_pnl_monthly >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_monthly)}</td>
            <td>${t.win_rate != null ? (t.win_rate * 100).toFixed(1) + '%' : '—'}</td>
            <td>${formatNumber(t.open_positions)}</td>
            <td><span class="badge badge-watched">WATCHED</span></td>
        </tr>
    `).join('');
}

// ============================================================
// Traders Page
// ============================================================
async function loadTraders() {
    const watchedOnly = document.getElementById('watched-only-toggle')?.checked;
    const url = watchedOnly ? '/traders?watched_only=true' : '/traders';

    try {
        const traders = await apiFetch(url);
        const tbody = document.getElementById('traders-tbody');
        tbody.innerHTML = traders.map((t, i) => `
            <tr>
                <td>${i + 1}</td>
                <td class="cell-name">${t.username || t.wallet.slice(0, 12) + '...'}</td>
                <td class="cell-highlight">${t.composite_score.toFixed(4)}</td>
                <td class="${t.best_pnl_all_time >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_all_time)}</td>
                <td class="${t.best_pnl_monthly >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_monthly)}</td>
                <td class="${t.best_pnl_weekly >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_weekly)}</td>
                <td class="${t.best_pnl_daily >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(t.best_pnl_daily)}</td>
                <td>${formatNumber(t.open_positions)}</td>
                <td><span class="badge ${t.is_watched ? 'badge-watched' : 'badge-unwatched'}">${t.is_watched ? 'YES' : 'NO'}</span></td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to load traders', err);
    }
}

// ============================================================
// Positions Page
// ============================================================
async function loadPositions() {
    try {
        const positions = await apiFetch('/positions');
        document.getElementById('position-count').textContent = `${positions.length} positions`;

        const tbody = document.getElementById('positions-tbody');
        tbody.innerHTML = positions.slice(0, 200).map(p => `
            <tr>
                <td class="cell-name">${p.trader_name || p.trader_wallet.slice(0, 12) + '...'}</td>
                <td title="${p.condition_id}">${p.condition_id.slice(0, 16)}...</td>
                <td><span class="badge badge-open">${p.outcome}</span></td>
                <td>${formatNumber(p.size, 2)}</td>
                <td>${p.avg_entry_price != null ? '$' + p.avg_entry_price.toFixed(4) : '—'}</td>
                <td>${p.current_value != null ? '$' + formatNumber(p.current_value) : '—'}</td>
                <td class="cell-neutral">${formatTime(p.first_detected_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to load positions', err);
    }
}

// ============================================================
// Signals Page
// ============================================================
async function loadSignals() {
    try {
        const signals = await apiFetch('/signals');
        const emptyState = document.getElementById('signals-empty');
        const tbody = document.getElementById('signals-tbody');

        if (signals.length === 0) {
            emptyState.style.display = 'block';
            tbody.innerHTML = '';
            return;
        }

        emptyState.style.display = 'none';
        tbody.innerHTML = signals.map(s => {
            const typeBadge = s.signal_type === 'OPEN' ? 'badge-open' :
                              s.signal_type === 'CLOSE' ? 'badge-close' :
                              s.signal_type === 'ADD' ? 'badge-add' : 'badge-pending';
            const statusBadge = s.status === 'APPROVED' ? 'badge-approved' :
                                s.status === 'REJECTED' ? 'badge-rejected' : 'badge-pending';
            return `
            <tr>
                <td>${s.id}</td>
                <td>${s.trader_wallet.slice(0, 12)}...</td>
                <td><span class="badge ${typeBadge}">${s.signal_type}</span></td>
                <td>${s.outcome}</td>
                <td class="${s.size_change >= 0 ? 'cell-positive' : 'cell-negative'}">${s.size_change >= 0 ? '+' : ''}${formatNumber(s.size_change, 2)}</td>
                <td>${s.market_price != null ? '$' + s.market_price.toFixed(4) : '—'}</td>
                <td><span class="badge ${statusBadge}">${s.status}</span></td>
                <td class="cell-neutral">${formatTime(s.created_at)}</td>
            </tr>`;
        }).join('');
    } catch (err) {
        console.error('Failed to load signals', err);
    }
}

// ============================================================
// Backtest Page
// ============================================================
async function runBacktest() {
    const btn = document.getElementById('btn-backtest');
    const loading = document.getElementById('backtest-loading');
    const results = document.getElementById('backtest-results');

    btn.disabled = true;
    loading.classList.remove('hidden');
    results.classList.add('hidden');

    try {
        const data = await apiFetch('/backtest', {
            method: 'POST',
            body: JSON.stringify({
                n_traders: parseInt(document.getElementById('bt-n-traders').value),
                capital: parseFloat(document.getElementById('bt-capital').value),
                slippage_bps: parseInt(document.getElementById('bt-slippage').value),
            }),
        });

        const tbody = document.getElementById('backtest-tbody');
        tbody.innerHTML = data.results.map(r => `
            <tr>
                <td class="cell-name">${r.trader_name || r.trader_wallet.slice(0, 12)}</td>
                <td>${r.trades_copied}</td>
                <td>${r.days_span}</td>
                <td class="${r.total_pnl >= 0 ? 'cell-positive' : 'cell-negative'}">$${formatNumber(r.total_pnl)}</td>
                <td class="${r.roi_pct >= 0 ? 'cell-positive' : 'cell-negative'}">${r.roi_pct.toFixed(1)}%</td>
                <td class="${r.daily_roi_pct >= 0 ? 'cell-positive' : 'cell-negative'}">${r.daily_roi_pct.toFixed(2)}%</td>
                <td>${(r.win_rate * 100).toFixed(1)}%</td>
                <td>$${formatNumber(r.slippage_cost)}</td>
            </tr>
        `).join('');

        results.classList.remove('hidden');
        showToast('Backtest complete!', 'success');
    } catch (err) {
        showToast('Backtest failed', 'error');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

// ============================================================
// Config Page
// ============================================================
async function loadConfig() {
    try {
        const configs = await apiFetch('/config');
        const grid = document.getElementById('config-grid');

        grid.innerHTML = configs.map(c => {
            const valueStr = typeof c.value === 'object' ? JSON.stringify(c.value, null, 2) : String(c.value);
            const isLong = valueStr.length > 50;
            return `
            <div class="config-item">
                <div class="config-key">${c.key}</div>
                <div class="config-desc">${c.description || '—'}</div>
                <div class="config-edit">
                    ${isLong
                        ? `<textarea id="cfg-${c.key}">${valueStr}</textarea>`
                        : `<input id="cfg-${c.key}" value='${valueStr.replace(/'/g, "&#39;")}'>`
                    }
                    <button class="config-save" onclick="saveConfig('${c.key}')">Save</button>
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        console.error('Failed to load config', err);
    }
}

async function saveConfig(key) {
    const el = document.getElementById(`cfg-${key}`);
    let value = el.value;

    // Try to parse as JSON
    try { value = JSON.parse(value); } catch { /* keep as string */ }

    try {
        await apiFetch(`/config/${key}`, {
            method: 'PUT',
            body: JSON.stringify({ value }),
        });
        showToast(`${key} updated`, 'success');
    } catch (err) {
        showToast(`Failed to update ${key}`, 'error');
    }
}

// ============================================================
// Actions
// ============================================================
async function refreshAll() {
    showToast('Refreshing...', 'info');
    await loadOverview();
    showToast('Refreshed!', 'success');
}

async function triggerCollect() {
    const btn = document.getElementById('btn-collect');
    btn.disabled = true;
    showToast('Collecting leaderboard data...', 'info');
    try {
        const data = await apiFetch('/collect', { method: 'POST' });
        showToast(`Collected! ${JSON.stringify(data.stats)}`, 'success');
        await loadOverview();
    } catch (err) {
        showToast('Collection failed', 'error');
    } finally {
        btn.disabled = false;
    }
}

async function triggerScore() {
    const btn = document.getElementById('btn-score');
    btn.disabled = true;
    showToast('Scoring traders...', 'info');
    try {
        const data = await apiFetch('/score', { method: 'POST' });
        showToast(`Scored! ${data.stats.eligible} eligible, ${data.stats.total_watched} watched`, 'success');
        await loadOverview();
    } catch (err) {
        showToast('Scoring failed', 'error');
    } finally {
        btn.disabled = false;
    }
}

// ============================================================
// Utilities
// ============================================================
function formatNumber(n, decimals = 0) {
    if (n == null || isNaN(n)) return '—';
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return parseFloat(n).toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ============================================================
// Crawl Runs Page
// ============================================================
async function loadCrawlRuns() {
    try {
        const runs = await apiFetch('/crawl/runs');
        const tbody = document.getElementById('crawl-runs-tbody');
        tbody.innerHTML = runs.map(r => {
            const dur = r.duration_seconds
                ? (r.duration_seconds > 3600
                    ? `${(r.duration_seconds/3600).toFixed(1)}h`
                    : `${Math.round(r.duration_seconds/60)}m`)
                : '—';
            const started = r.started_at
                ? new Date(r.started_at).toLocaleString()
                : '—';
            const newEvt = r.new_events
                ? r.new_events.toLocaleString()
                : '0';
            const modeClass = r.mode === 'resync' ? 'text-warning' : '';
            return `<tr>
                <td>${r.id}</td>
                <td>${started}</td>
                <td>${dur}</td>
                <td class="${modeClass}">${r.mode}</td>
                <td>${r.total_traders}</td>
                <td class="text-positive">${r.ok}</td>
                <td class="text-warning">${r.warn}</td>
                <td class="text-negative">${r.errors}</td>
                <td>${r.resynced}</td>
                <td>${newEvt}</td>
                <td class="text-muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${r.notes || '—'}</td>
            </tr>`;
        }).join('');

        if (runs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;opacity:0.5">No runs recorded yet</td></tr>';
        }
    } catch (err) {
        console.error('Failed to load crawl runs', err);
    }
}

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    loadOverview();
    // Auto-refresh every 30 seconds
    setInterval(() => {
        const activePage = document.querySelector('.page.active');
        if (activePage?.id === 'page-overview') loadOverview();
    }, 30000);
});
