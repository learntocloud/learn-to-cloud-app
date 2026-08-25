(function () {
    'use strict';

    function pageUri() {
        return window.location.origin + window.location.pathname;
    }

    var lastTrackedUrl = pageUri();

    function appInsights() {
        if (window.appInsights && typeof window.appInsights.trackEvent === 'function') {
            return window.appInsights;
        }
        return null;
    }

    function trackHtmxPageView() {
        var telemetry = appInsights();
        var currentUrl = pageUri();
        if (!telemetry || currentUrl === lastTrackedUrl) {
            return;
        }

        lastTrackedUrl = currentUrl;
        telemetry.trackPageView({
            name: document.title,
            uri: currentUrl,
            properties: {
                navigationType: 'htmx'
            }
        });
    }

    function trackHtmxTransportError(event) {
        var telemetry = appInsights();
        if (!telemetry || !event.detail) {
            return;
        }

        var requestConfig = event.detail.requestConfig || {};
        telemetry.trackEvent({
            name: 'htmx.transport_error',
            properties: {
                method: requestConfig.verb || '',
                boosted: String(Boolean(event.detail.boosted))
            }
        });
    }

    document.addEventListener('htmx:afterSettle', function (event) {
        if (event.detail && event.detail.boosted) {
            trackHtmxPageView();
        }
    });

    document.addEventListener('htmx:sendError', function (event) {
        trackHtmxTransportError(event);
    });
})();
