# Hands-On Verification System

This document describes the hands-on verification system used to validate learner progress through practical challenges.

## Overview

The verification system validates submissions for hands-on requirements across all phases. Each requirement has a specific submission type that determines how it's validated.

## Submission Types

| Type | Description | Validator |
|------|-------------|-----------|
| `PROFILE_README` | GitHub profile README exists | GitHub API |
| `REPO_FORK` | User forked a specific repository | GitHub API |
| `REPO_HAS_FILES` | Repository contains required files | GitHub API |
| `REPO_URL` | Valid repository URL | GitHub API |
| `WORKFLOW_RUN` | GitHub Actions workflow completed | GitHub API |
| `CONTAINER_IMAGE` | Container image exists in registry | Registry API |
| `GITHUB_PROFILE` | GitHub profile validation | GitHub API |
| `DEPLOYED_APP` | App is deployed and responding | HTTP request |
| `JOURNAL_API` | Journal API returns valid response | HTTP request |
| `CTF_TOKEN` | CTF completion token | HMAC verification |

## CTF Token Verification

### Purpose

The CTF (Capture The Flag) verification validates completion of the Linux CTF challenges. Users complete 18 challenges in a sandboxed Linux environment and receive a signed token upon completion.

### Token Structure

Tokens are base64-encoded JSON with the following structure:

```json
{
  "payload": {
    "github_username": "user123",
    "instance_id": "unique-instance-id",
    "challenges": 18,
    "timestamp": 1737312000,
    "date": "2026-01-19",
    "time": "12:00:00"
  },
  "signature": "hmac-sha256-hex-signature"
}
```

### Security Model

1. **HMAC Signature**: Tokens are signed using HMAC-SHA256 with a derived secret
2. **Secret Derivation**: Per-instance secrets are derived from the master secret and instance ID
3. **Username Binding**: Tokens are bound to the GitHub username — a token generated for one user cannot be used by another
4. **Challenge Count**: All 18 challenges must be completed
5. **Timing-Safe Comparison**: Uses `hmac.compare_digest()` to prevent timing attacks

### Token Lifetime

Tokens do **not expire**. This is intentional because:
- Tokens are reused across multiple phases (e.g., Phase 1 completion, later phase references)
- Username binding prevents token sharing
- The CTF environment may not always be available for re-completion

### JSON Serialization Requirements

**CRITICAL**: Token generation and verification must use identical JSON serialization.

The verification uses:
```python
json.dumps(payload, separators=(",", ":"))
```

This produces compact JSON with:
- No whitespace after separators
- Keys in insertion order (Python 3.7+ guarantees this)

Token generators (e.g., the CTF challenge environment) **must** use the same serialization format, or signature verification will fail.

### Verification Flow

```
┌─────────────────┐
│  User submits   │
│  base64 token   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Decode base64  │──── Invalid ──▶ Reject
│  Parse JSON     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Check username  │──── Mismatch ──▶ Reject
│ matches OAuth   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Derive secret   │
│ from instance   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Verify HMAC     │──── Invalid ──▶ Reject
│ signature       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Check challenge │──── < 18 ──▶ Reject
│ count = 18      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validate        │──── Future ──▶ Reject
│ timestamp       │
└────────┬────────┘
         │
         ▼
    ✅ Success

```

### Environment Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `CTF_MASTER_SECRET` | Master secret for HMAC signing | Yes (production) |

The master secret must be:
- Set in all non-development environments
- Different from the default value
- Shared between the CTF challenge environment and the API

## Deployed App Verification

Validates that a user has deployed an application to a public URL.

### Security Measures

- **SSRF Prevention**: Only public IP addresses are allowed (blocks localhost, private IPs, link-local)
- **Circuit Breaker**: Protects against cascading failures from unresponsive apps
- **Timeout**: HTTP requests timeout after configured duration

## GitHub Verification

All GitHub-based validations:
- Use the GitHub API with authentication
- Validate that the repository/resource belongs to the authenticated user
- Are case-insensitive for username matching

## Adding New Verification Types

1. Add the `SubmissionType` enum value in `models.py`
2. Add optional fields to `HandsOnRequirement` in `schemas.py` if needed
3. Create a validator function in the appropriate service module
4. Add routing case in `validate_submission()` in `hands_on_verification_service.py`
