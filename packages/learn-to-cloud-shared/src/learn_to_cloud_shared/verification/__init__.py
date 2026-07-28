"""Verification subsystem for hands-on learning requirements.

Runs inside the Durable Function verify step. Submodules:
    engine            - Declarative profile registry that routes each type
    events            - In-process event bus for async verification results
    github_profile    - Profile README/fork verification
    ci_status         - CI test-pass check
    token_base        - HMAC token verification for CTF + Networking Lab
    devops_analysis   - DevOps artifact analysis
    security_scanning - Dependabot + CodeQL verification
    deployed_api      - Live API challenge-response testing
    errors            - Verification error types and error-to-result mappers
    tasks/            - Task definitions per phase
"""
