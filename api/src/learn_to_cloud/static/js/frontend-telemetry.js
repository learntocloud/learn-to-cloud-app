(function () {
    'use strict';

    var lastTrackedUrl = window.location.href;

    function appInsights() {
        if (window.appInsights && typeof window.appInsights.trackEvent === 'function') {
            return window.appInsights;
        }
        return null;
    }

    function trackHtmxPageView() {
        var telemetry = appInsights();
        if (!telemetry || window.location.href === lastTrackedUrl) {
            return;
        }

        lastTrackedUrl = window.location.href;
        telemetry.trackPageView({
            name: document.title,
            uri: window.location.href,
            properties: {
                navigationType: 'htmx'
            }
        });
    }

    function trackHtmxError(eventName, event) {
        var telemetry = appInsights();
        if (!telemetry || !event.detail) {
            return;
        }

        var xhr = event.detail.xhr;
        var requestConfig = event.detail.requestConfig || {};
        telemetry.trackEvent({
            name: eventName,
            properties: {
                method: requestConfig.verb || '',
                path: requestConfig.path || '',
                statusCode: xhr && xhr.status ? String(xhr.status) : '',
                boosted: String(Boolean(event.detail.boosted))
            }
        });
    }

    document.addEventListener('htmx:afterSettle', function (event) {
        if (event.detail && event.detail.boosted) {
            trackHtmxPageView();
        }
    });

    document.addEventListener('htmx:responseError', function (event) {
        trackHtmxError('htmx.response_error', event);
    });

    document.addEventListener('htmx:sendError', function (event) {
        trackHtmxError('htmx.send_error', event);
    });
})();
