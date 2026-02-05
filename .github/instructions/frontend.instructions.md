---
applyTo: "frontend/src/**/*.{ts,tsx,js,jsx}"
description: "React hooks, TanStack Query v5, Clerk auth, TypeScript strict typing, Tailwind CSS v4"
---

# Vite/React/TypeScript Coding Standards

## TypeScript
- **Never** use `any`—use `unknown` if truly unknown
- Use `import type { }` for type-only imports
- Write type guards instead of `as` assertions

## API Contract & Types
- API types are hand-written in `frontend/src/lib/types.ts`
- When you change a Pydantic schema in `api/schemas.py`, update the matching TypeScript type in `types.ts`
- No codegen step — there is no `openapi.json` → TypeScript pipeline
- Use `createApiClient()` from `api-client.ts` instead of ad-hoc `fetch` calls

## React Hooks
- Call hooks at **top level only**—never in conditionals/loops
- Include **all** dependencies in hook arrays (don't disable ESLint rule)
- `useEffect` cleanup required for subscriptions, timers, listeners
- `useCallback` for functions passed as props; `useMemo` only for expensive computations

## TanStack Query v5

### Query Keys
- Keys must include **all** variables: `['topic', phaseSlug, topicSlug]`
- Use consistent key factories across the codebase

### Configuration
- **Always** set `staleTime` explicitly (default is 0)
- Use `enabled` for conditional fetching: `enabled: !!userId`
- Distinguish `isLoading` vs `isPending` vs `isFetching`

### Mutations
- Call `invalidateQueries` after successful mutations
- For optimistic updates: `onMutate` with rollback in `onError`

## Clerk React
- `useAuth()` for `getToken`, `isSignedIn`, `userId`
- `useUser()` for profile data
- `<SignedIn>` / `<SignedOut>` for conditional rendering
- Always pass token to API calls via `getToken()`

## React Router v7
- Route order matters: specific routes before `/:param` routes
- Use `useNavigate()` or `<Link>` (not `window.location`)

## Vite/Build
- Environment variables: `import.meta.env.VITE_*` (not `process.env`)
- Path aliases (`@/`) must be in both `tsconfig.json` and `vite.config.ts`
- **Never** use Node.js APIs in browser code

## Tailwind CSS v4
- Order responsive prefixes consistently: `sm:`, `md:`, `lg:`, `xl:`
- Avoid conflicting utility classes on same element

## Accessibility
- ARIA labels on icon-only buttons
- Form inputs must have associated labels
- Manage focus on route changes

## Testing (Vitest + Testing Library)
- Mock with `vi.mock()` and `vi.fn()`
- Wrap components with required providers in tests
- Use `waitFor` or `findBy*` for async operations

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
