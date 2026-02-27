/**
 * Status page chart initialization.
 *
 * Reads chart data from a <script type="application/json"> element
 * and renders Chart.js charts with dark-mode support.
 * Also animates stat card numbers with a count-up effect.
 */
(function () {
    // ── Count-up animation for stat numbers ──
    function countUp(el, target, duration) {
        var startTime = null;
        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / duration, 1);
            var eased = 1 - (1 - progress) * (1 - progress);
            el.textContent = Math.floor(eased * target).toLocaleString();
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    function initCountUp() {
        var els = document.querySelectorAll('[data-count-target]');
        for (var i = 0; i < els.length; i++) {
            var target = parseInt(els[i].getAttribute('data-count-target'), 10);
            if (!isNaN(target) && target > 0) {
                countUp(els[i], target, 1200);
            }
        }
    }

    initCountUp();

    // ── Chart.js lazy loading ──
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

    var PROVIDER_COLORS = {
        'AWS': '#FF9900',
        'AZURE': '#0078D4',
        'GCP': '#4285F4'
    };
    var PROVIDER_FALLBACK_COLOR = '#9CA3AF';

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

        // ── Verification / Phase Difficulty Chart (horizontal bar) ──
        if (data.verification) {
            var verifCtx = document.getElementById('verificationChart');
            if (verifCtx) {
                swapToCanvas('verificationFallback', 'verificationChartWrap');
                var passRateColors = data.verification.passRates.map(function (rate) {
                    if (rate >= 70) return isDark ? 'rgba(34, 197, 94, 0.7)' : 'rgba(34, 197, 94, 0.8)';
                    if (rate >= 40) return isDark ? 'rgba(234, 179, 8, 0.7)' : 'rgba(234, 179, 8, 0.8)';
                    return isDark ? 'rgba(239, 68, 68, 0.7)' : 'rgba(239, 68, 68, 0.8)';
                });
                new Chart(verifCtx, {
                    type: 'bar',
                    data: {
                        labels: data.verification.labels,
                        datasets: [{
                            label: 'Pass Rate %',
                            data: data.verification.passRates,
                            backgroundColor: passRateColors,
                            borderRadius: 4,
                        }]
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { min: 0, max: 100, ticks: { callback: function (v) { return v + '%'; } }, grid: { color: gridColor } },
                            y: { grid: { display: false } }
                        }
                    }
                });
            }
        }

        // ── Cloud Providers Doughnut ──
        if (data.providers) {
            var provCtx = document.getElementById('providersChart');
            if (provCtx) {
                swapToCanvas('providersFallback', 'providersChartWrap');
                var bgColors = data.providers.labels.map(function (label) {
                    return PROVIDER_COLORS[label] || PROVIDER_FALLBACK_COLOR;
                });
                new Chart(provCtx, {
                    type: 'doughnut',
                    data: {
                        labels: data.providers.labels,
                        datasets: [{
                            data: data.providers.counts,
                            backgroundColor: bgColors,
                            borderColor: isDark ? '#1F2937' : '#FFFFFF',
                            borderWidth: 2,
                            borderRadius: 4,
                            spacing: 2,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '65%',
                        plugins: {
                            legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } }
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

        // ── Weekly Activity Bar Chart ──
        if (data.activity) {
            var actCtx = document.getElementById('activityChart');
            if (actCtx) {
                swapToCanvas('activityFallback', 'activityChartWrap');
                new Chart(actCtx, {
                    type: 'bar',
                    data: {
                        labels: data.activity.labels,
                        datasets: [{
                            label: 'Steps Completed',
                            data: data.activity.completions,
                            backgroundColor: isDark ? 'rgba(59, 130, 246, 0.6)' : 'rgba(59, 130, 246, 0.7)',
                            borderRadius: 4,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: gridColor } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }
        }
    }

    loadChartJs(initCharts);
})();
