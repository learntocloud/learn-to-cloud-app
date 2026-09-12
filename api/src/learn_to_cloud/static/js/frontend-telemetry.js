(function () {
    'use strict';

    var telemetry = window.appInsights;
    if (!telemetry) {
        return;
    }

    function cleanUrl(value) {
        var url = new URL(value, window.location.origin);
        url.username = '';
        url.password = '';
        url.search = '';
        url.hash = '';
        return url.href;
    }

    telemetry.addTelemetryInitializer(function (envelope) {
        var data = envelope.baseData;
        if (data) {
            ['uri', 'url', 'refUri'].forEach(function (key) {
                if (data[key]) {
                    data[key] = cleanUrl(data[key]);
                }
            });
            if (envelope.baseType === 'RemoteDependencyData') {
                data.target = cleanUrl(data.target);
                data.name = data.name.split(/[?#]/, 1)[0];
            }
            if (envelope.baseType === 'ExceptionData') {
                // The SDK merges both sources into the exported properties.
                [data.properties, envelope.data].forEach(function (properties) {
                    if (properties) {
                        if (properties.url) {
                            properties.url = cleanUrl(properties.url);
                        }
                        delete properties.errorSrc;
                    }
                });
            }
        }
        return true;
    });
    telemetry.loadAppInsights();
    telemetry.trackPageView();

    function eventProperties(element) {
        return {
            phase: element.dataset.telemetryPhase || '',
            nextPhase: element.dataset.telemetryNextPhase || '',
            phaseOptional: element.dataset.telemetryPhaseOptional || '',
            nextPhaseOptional: element.dataset.telemetryNextPhaseOptional || '',
            transitionId: element.dataset.telemetryTransitionId || ''
        };
    }

    function trackViewEvents(root) {
        if (!root || !root.querySelectorAll) {
            return;
        }
        root.querySelectorAll('[data-telemetry-view-event]').forEach(function (element) {
            if (element.dataset.telemetryTracked === 'true') {
                return;
            }
            element.dataset.telemetryTracked = 'true';
            telemetry.trackEvent(
                { name: element.dataset.telemetryViewEvent },
                eventProperties(element)
            );
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        trackViewEvents(document);
    });
    document.addEventListener('click', function (event) {
        if (!event.target || !event.target.closest) {
            return;
        }
        var element = event.target.closest('[data-telemetry-event]');
        if (!element) {
            return;
        }
        telemetry.trackEvent(
            { name: element.dataset.telemetryEvent },
            eventProperties(element)
        );
    });

    // SDK history tracking counts HTMX's replaceState + pushState twice.
    document.addEventListener('htmx:afterSettle', function (event) {
        if (event.detail && event.detail.boosted) {
            telemetry.trackPageView();
            trackViewEvents(event.detail.elt || document);
        }
    });
    document.addEventListener('htmx:historyRestore', function () {
        telemetry.trackPageView();
    });
})();
