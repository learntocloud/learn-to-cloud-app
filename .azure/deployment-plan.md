# Deployment Plan: Verification Functions telemetry

## Status

Approved for Execution

## Scope

Modify the existing Python Azure Durable Functions app in `apps/verification-functions` so it emits telemetry consistently with the FastAPI API.

## Decisions

- Reuse the existing shared Application Insights resource by setting the Function App `APPLICATIONINSIGHTS_CONNECTION_STRING` to the same value used by the API.
- Keep API and Function telemetry separated in Application Map with distinct `OTEL_SERVICE_NAME` values.
- Enable Azure Functions host OpenTelemetry output and Durable Functions distributed tracing in `host.json`.
- Initialize the existing shared Python observability setup from the Function worker entry point.
- Enable local Aspire export through `OTEL_EXPORTER_OTLP_ENDPOINT` for local Function runs.

## Changes

- Update `apps/verification-functions/function_app.py`.
- Update `apps/verification-functions/host.json`.
- Update `apps/verification-functions/local.settings.example.json`.
- Update local VS Code launch configuration for Function telemetry.
- Ensure Function runtime dependencies include Azure Monitor OpenTelemetry.

## Validation

- Run formatting/type checks for the modified Python Function app where available.
