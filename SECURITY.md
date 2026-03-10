# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch (latest) | Yes |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT open a public GitHub issue.**
2. Use [GitHub Security Advisories](https://github.com/learntocloud/learn-to-cloud-app/security/advisories/new) to privately report the vulnerability.
3. Include as much detail as possible: steps to reproduce, affected components, and potential impact.

## Response Timeline

- **Acknowledgment**: Within 3 business days of receiving the report.
- **Assessment**: We will assess severity and impact within 7 business days.
- **Fix**: Critical and high severity issues will be prioritized for the next release.

## Scope

The following are in scope for security reports:

- The Learn to Cloud web application ([api/](api/))
- Infrastructure configuration ([infra/](infra/))
- CI/CD workflows ([.github/workflows/](.github/workflows/))
- Authentication and session management
- Data handling and storage

## Out of Scope

- Third-party services and dependencies (report directly to the vendor)
- Social engineering attacks
- Denial of service attacks against production infrastructure
