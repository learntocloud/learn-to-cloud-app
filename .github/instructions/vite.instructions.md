---
applyTo: '**/*.{ts,tsx,js,jsx}'
---

# Vite/React/TypeScript Coding Standards

## TypeScript

### Strict Typing
- **Never** use `any` type—use `unknown` if truly unknown
- Use generic constraints where appropriate: `function fetch<T extends BaseModel>()`
- Prefer `as const` for literal types
- Use `import type { }` when importing only types
- Handle nullability with `?.` and `??` operators
- Write type guards for runtime checks instead of type assertions (`as`)

### Modern Syntax
- Use template literals for string interpolation
- Prefer `const` over `let` when value won't change
- Use destructuring for object/array access
- Prefer arrow functions for callbacks

## React

### Hooks Rules
- Call hooks at the **top level only**—never in conditionals, loops, or nested functions
- Custom hooks must start with `use` prefix
- Every `useEffect` should have a cleanup function when dealing with subscriptions, timers, or event listeners

### Dependency Arrays
- Include **all** dependencies used inside hooks in the dependency array
- Use `useCallback` for functions passed to child components to prevent re-renders
- Use `useMemo` only for expensive computations—don't over-optimize
- If ESLint warns about missing dependencies, fix it (don't disable the rule)

### Component Patterns
- Use keys on list items (never use array index as key for dynamic lists)
- Prefer controlled components for forms
- Use `React.lazy()` + `<Suspense>` for code splitting with proper fallback UI
- Place error boundaries near lazy-loaded components

### Performance
- Memoize callbacks with `useCallback` when passed as props
- Memoize expensive computations with `useMemo`
- Avoid creating objects/arrays inline in JSX (causes re-renders)
- Use `React.memo()` for components that render often with same props

## TanStack Query v5

### Query Keys
- Keys must be unique and include **all** variables: `['topic', phaseSlug, topicSlug]`
- Use consistent key factories across the codebase

### Configuration
- **Always** set `staleTime` explicitly (default is 0)
- Consider `gcTime` (formerly `cacheTime`) for memory management
- Use `enabled` option for conditional fetching: `enabled: !!userId`

### Data Handling
- Use `select` option for data transformation (not in render)
- Handle loading states: distinguish `isLoading` vs `isPending` vs `isFetching`
- Implement error handling with `onError` or error boundaries
- Use `useQueryClient()` for manual cache invalidation

### Mutations
- Use `useMutation` for POST/PUT/DELETE operations
- Call `invalidateQueries` after successful mutations
- For optimistic updates, implement `onMutate` with rollback in `onError`

## Clerk React

- Wrap app with `<ClerkProvider>` and correct `publishableKey`
- Use `useAuth()` for `getToken`, `isSignedIn`, `userId`
- Use `useUser()` for user profile data
- Use `<SignedIn>` / `<SignedOut>` for conditional rendering
- Always pass token to API calls via `getToken()`

## React Router v7

- Route order matters: specific routes before dynamic `/:param` routes
- Use `useParams()` with proper TypeScript typing
- Use `useNavigate()` or `<Link>` for navigation (not `window.location`)
- Implement protected routes pattern for authenticated content

## Vite/Build

- Environment variables: `import.meta.env.VITE_*` (not `process.env`)
- Use dynamic imports with `lazy()` for code splitting
- Import assets properly (not string paths)
- Path aliases (`@/`) must be configured in both `tsconfig.json` and `vite.config.ts`
- **Never** use Node.js APIs in browser code

## Tailwind CSS v4

- Use `@tailwindcss/postcss` in PostCSS config
- Order responsive prefixes consistently: `sm:`, `md:`, `lg:`, `xl:`
- Avoid conflicting utility classes on same element
- Use `@apply` sparingly (only in CSS files, not inline)

## Accessibility

- All interactive elements must be focusable
- Add ARIA labels on icon-only buttons
- Form inputs must have associated labels
- Ensure color contrast meets WCAG AA
- Manage focus on route changes
- Provide screen reader announcements for dynamic content

## Testing (Vitest + Testing Library)

- Tests use `describe`, `it`, `expect` from Vitest
- Component tests use `render`, `screen` from Testing Library
- User interactions via `@testing-library/user-event`
- Async operations with `waitFor` or `findBy*` queries
- Mock with `vi.mock()` and `vi.fn()`
- Wrap components with required providers (TanStack Query, Clerk) in tests

## Imports

- Group imports: React → third-party → local (`@/`)
- No unused imports
- No circular dependencies

## Special Comments
- `// @ts-ignore` — always add justification on same or previous line
- Skip `@param` in JSDoc when TypeScript types are present
