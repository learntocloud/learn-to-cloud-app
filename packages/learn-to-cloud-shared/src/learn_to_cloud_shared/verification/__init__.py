"""Verification subsystem for hands-on learning requirements.

Runs inside the Durable Function verify step. Submodules:
    core              - Typed check, step, and workflow contracts
    checks/           - Directly callable verification adapters
    workflows          - Ordered workflow catalog for every submission type
    engine            - Ownership, execution, telemetry, and grading preparation
    events            - In-process event bus for async verification results
    github_profile    - Profile README/fork verification
    ci_status         - CI test-pass check
    token_base        - HMAC token verification for CTF + Networking Lab
    devops_analysis   - Current-commit delivery workflow and job results
    security_scanning - Dependabot + CodeQL verification
    deployed_api      - Live journal creation and AI analysis
    errors            - Verification error types and error-to-result mappers
    tasks/            - Task definitions per phase
"""
