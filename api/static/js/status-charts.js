/**
 * Status page chart initialization.
 *
 * Reads chart data from a <script type="application/json"> element
 * and renders Chart.js funnel + growth charts with dark-mode support.
 */
(function () {
    function loadChartJs(cb) {
        if (typeof Chart !== 'undefined') { cb(); return; }
        var s = document.createElement('script');
        s.src = '/static/js/chart.umd.min.js';
        s.onload = cb;
        document.head.appendChild(s);
    }

    function swapToCanvas(fallbackId, canvasWrapId) {
        var fb = document.getElementById(fallbackId);
        var cw = document.getElementById(canvasWrapId);
        if (fb) fb.style.display = 'none';
        if (cw) cw.classList.remove('hidden');
    }

    function initCharts() {
        if (typeof Chart === 'undefined') return;

        var dataEl = document.getElementById('chart-data');
        if (!dataEl) return;
        var data = JSON.parse(dataEl.textContent);

        var isDark = document.documentElement.classList.contains('dark');
        var textColor = isDark ? '#9CA3AF' : '#6B7280';
        var gridColor = isDark ? 'rgba(75, 85, 99, 0.3)' : 'rgba(209, 213, 219, 0.5)';

        Chart.defaults.color = textColor;
        Chart.defaults.borderColor = gridColor;

        // ── Funnel Chart ──
        if (data.funnel) {
            var funnelCtx = document.getElementById('funnelChart');
            if (funnelCtx) {
                swapToCanvas('funnelFallback', 'funnelChartWrap');
                new Chart(funnelCtx, {
                    type: 'bar',
                    data: {
                        labels: data.funnel.labels,
                        datasets: [
                            {
                                label: 'Reached',
                                data: data.funnel.reached,
                                backgroundColor: isDark ? 'rgba(59, 130, 246, 0.7)' : 'rgba(59, 130, 246, 0.8)',
                                borderRadius: 4,
                            },
                            {
                                label: 'Completed Steps',
                                data: data.funnel.completed,
                                backgroundColor: isDark ? 'rgba(34, 197, 94, 0.7)' : 'rgba(34, 197, 94, 0.8)',
                                borderRadius: 4,
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: gridColor } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }
        }

        // ── Growth Chart ──
        if (data.growth) {
            var growthCtx = document.getElementById('growthChart');
            if (growthCtx) {
                swapToCanvas('growthFallback', 'growthChartWrap');
                new Chart(growthCtx, {
                    type: 'line',
                    data: {
                        labels: data.growth.labels,
                        datasets: [
                            {
                                label: 'Total Learners',
                                data: data.growth.cumulative,
                                borderColor: '#3B82F6',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                fill: true,
                                tension: 0.3,
                                pointRadius: 2,
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: gridColor } },
                            x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }
                        }
                    }
                });
            }
        }
    }

    loadChartJs(initCharts);
})();
