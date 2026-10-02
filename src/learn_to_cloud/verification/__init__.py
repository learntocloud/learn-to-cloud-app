"""Verification subsystem for hands-on learning requirements.

Runs inside the API verification worker. Submodules:
    core              - Check result contracts
    engine            - Ownership, check dispatch, telemetry, and grading preparation
    github_profile    - Profile README/fork results from ownership metadata
    ci_status         - CI test-pass check
    token_base        - HMAC token verification for CTF + Networking Lab
    devops_analysis   - Current-commit delivery workflow and job results
    security_scanning - CodeQL gate + scanning config evidence
    deployed_api      - Live journal creation and AI analysis
    errors            - Verification error types and error-to-result mappers
    tasks/            - Task definitions per phase
"""
