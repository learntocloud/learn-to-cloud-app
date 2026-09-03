(function () {
    'use strict';

    function pageUri() {
        var marker = document.querySelector('[data-telemetry-route]');
        var route = marker ? marker.getAttribute('data-telemetry-route') : '/unmatched';
        return window.location.origin + route;
    }

    function appInsights() {
        if (window.appInsights && typeof window.appInsights.trackEvent === 'function') {
            return window.appInsights;
        }
        return null;
    }

    function removeUrlProperties(envelope) {
        var baseData = envelope && envelope.baseData;
        if (!baseData) {
            return true;
        }

        delete baseData.refUri;
        if (envelope.baseType === 'PageviewData') {
            baseData.uri = pageUri();
        }
        return true;
    }

    function trackPageView(navigationKind) {
        var telemetry = appInsights();
        var currentUrl = pageUri();
        if (!telemetry) {
            return;
        }

        telemetry.trackPageView({
            name: document.title,
            uri: currentUrl,
            properties: {
                'navigation.type': navigationKind
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
                'http.request.method': requestConfig.verb || '',
                'htmx.boosted': Boolean(event.detail.boosted)
            }
        });
    }

    var telemetry = appInsights();
    if (telemetry) {
        telemetry.addTelemetryInitializer(removeUrlProperties);
        trackPageView('initial');
    }

    document.addEventListener('htmx:afterSettle', function (event) {
        if (event.detail && event.detail.boosted) {
            trackPageView('htmx');
        }
    });

    document.addEventListener('htmx:historyRestore', function () {
        trackPageView('history');
    });

    document.addEventListener('htmx:sendError', function (event) {
        trackHtmxTransportError(event);
    });
})();
