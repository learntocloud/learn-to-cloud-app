# Authentication and sessions

GitHub OAuth establishes identity; PostgreSQL-backed sessions keep it revocable.
The `ltc_session` cookie is an opaque credential, not an encoded user ID.
Only its digest is stored. The separate signed `session` cookie is temporary
OAuth handshake state, not proof of login; signed does not mean encrypted.

## Guarantees to preserve

- Use the numeric GitHub ID as the account key. Usernames and display names can
  change. Validate provider identity without coercing malformed IDs, including
  after username normalization, and verify that the persisted identity matches.
- Commit profile persistence and session creation before issuing a login cookie
  or reporting successful login.
- Resolve the current account from the session store, not from legacy cookie
  identity fields. Missing, revoked, expired, and deleted-account sessions cannot
  authenticate. A database outage is a service failure, not anonymous access.
- Keep authentication cookies HttpOnly, SameSite=Lax, host-only, and Secure in
  production. Identity-dependent responses must not enter shared caches.
- Failed OAuth attempts must not replace an existing login or discard unrelated
  in-flight OAuth state.

Sessions expire after seven inactive days or thirty days from issuance, whichever
comes first. The server is authoritative: an open page or unexpired browser
cookie cannot extend a session. Authenticated polling counts as activity;
static assets and health probes do not. Expired rows are pruned opportunistically
at login, with no scheduled removal guarantee.

Validation rules and configurable limits live in
[`core/auth.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/src/learn_to_cloud/core/auth.py)
and shared
[`SessionConfig`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/packages/learn-to-cloud-shared/src/learn_to_cloud_shared/core/config.py).

## Adding authenticated routes

Import dependencies from `learn_to_cloud.core.auth`:

| Route needs | Dependency |
|-------------|------------|
| ID and username only | `CurrentUser` |
| Profile fields or account-aware templates | `CurrentAccount` |
| An account when signed in, otherwise anonymous access | `OptionalCurrentAccount` |

Resolution is cached only for the request and releases its transaction before
route work. Pass the loaded account explicitly to rendering helpers; do not
query it again or reach through `request.state`.
Treat it as a read-only ORM snapshot: no mutation, lazy-loading, or attachment
to a write session. Use an explicit service transaction for writes.

Protected page routers use `LoginRedirectRoute`; JSON and HTMX endpoints do not.
Do not infer authentication response policy from URL prefixes or `Accept`.

| Unauthenticated request | Response |
|-------------------------|----------|
| JSON or HTMX endpoint | 401, no login redirect |
| Protected page navigation | 303 to `/auth/login` |
| Protected page with `HX-Request: true` | 401; the frontend navigates to login |

Use 303 for browser mutations that redirect so the next request is GET.

## Logout and account deletion

Current-browser logout revokes that session before clearing cookies. A copied
cookie must then fail across processes; other browser sessions stay valid.
Repeat logout safely for absent or invalid credentials, but never claim
revocation succeeded when its database transaction failed.

Sign out everywhere requires a live session and session-bound CSRF confirmation.
Account-wide mutations and login issuance use account-before-session locking;
preserve that order and recheck the requesting session under the lock.
Account deletion commits the account and its session/progress/submission cascades
atomically before reporting success.

Revocation takes effect at commit. Already-authorized work may finish, and a
genuinely later login can create a new session. Recreating a deleted account
never revives old sessions. These actions do not revoke GitHub authorization.

## Profile names

Preserve nonblank names as supplied, including Unicode and whitespace; do not
split or truncate them. Missing or unusable optional names do not block login.
Render names as escaped text and fall back to username when no name is stored.
Do not deliberately add profile values to telemetry. Database diagnostics retain
the tradeoff described in [Telemetry](telemetry.html).

## Changing authentication

Exercise real routes and middleware, cookie replay, independent browsers, and
commit failures. Auth overrides are appropriate for unrelated rendering tests,
not tests of authentication itself. Start with
[`test_auth_http.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/tests/routes/test_auth_http.py)
and
[`test_session_lifecycle.py`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/api/tests/routes/test_session_lifecycle.py).
