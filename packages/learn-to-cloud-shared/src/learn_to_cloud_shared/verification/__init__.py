"""Verification subsystem for hands-on learning requirements.

Runs inside the Durable Function verify step. Submodules:
    dispatcher        - Routes submissions to the matching validator
    events            - In-process event bus for async verification results
    github_profile    - GitHub profile/README/fork verification
    ci_status         - CI test-pass check
    token_base        - HMAC token verification for CTF + Networking Lab
    devops_analysis   - DevOps artifact analysis
    security_scanning - Dependabot + CodeQL verification
    deployed_api      - Live API challenge-response testing
    repo_utils        - GitHub URL parsing and identity resolution
    tasks/            - Task definitions per phase
"""
