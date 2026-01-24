---
name: frontend-library-review
description: Deep dive review of TypeScript/JavaScript/React/Vite file - fetches official docs, searches best practices, audits all usages in codebase. Use when user says "review file", "review this file", or "analyze this code" on a .ts, .tsx, .js, or .jsx file. This is NOT a surface-level review.
---

# Frontend Library & Pattern Deep Dive Review

**THIS IS NOT A SURFACE-LEVEL REVIEW.**

For every third-party library in the file, you MUST:
1. Fetch official documentation
2. Search for best practices and common pitfalls
3. Find all usages in the codebase
4. Compare documented behavior against actual implementation
5. Cite sources for every claim

**Time/token budget**: This review is intentionally exhaustive. It may take significant time and tokens. That is expected and correct.

---

## When to Use

- User says "review file" or "review this file" on a `.ts`, `.tsx`, `.js`, or `.jsx` file
- User asks to "analyze imports" or "explain the patterns"
- User wants to understand libraries used in frontend code

---

## PHASE 1: Inventory (Required First Step)

### Step 1.1: Extract All Imports

Read the file and create a categorized list:

```markdown
## Import Inventory

### Built-in/Runtime APIs
| Import/API | Used For |
|------------|----------|
| `fetch` | HTTP requests |
| `localStorage` | Client-side storage |

### Third-Party Libraries (REQUIRE DEEP RESEARCH)
| Import | Library | Doc URL |
|--------|---------|---------|
| `useQuery` | @tanstack/react-query | https://tanstack.com/query/latest |
| `z` | zod | https://zod.dev |

### Framework Imports
| Import | Framework | Doc URL |
|--------|-----------|---------|
| `useState`, `useEffect` | React | https://react.dev |

### Local Imports
| Import | File Path |
|--------|-----------|
| `useAuth` | `@/hooks/useAuth.ts` |
| `Button` | `@/components/ui/Button.tsx` |
```

### Step 1.2: Identify Patterns

List all patterns used:
- React Hooks (custom hooks, built-in hooks)
- Component patterns (compound, render props, HOC)
- State management patterns (context, stores, reducers)
- Data fetching patterns (queries, mutations, optimistic updates)
- Form patterns (controlled, uncontrolled, validation)
- TypeScript patterns (generics, type guards, discriminated unions)

---

## PHASE 2: Deep Library Research (MANDATORY)

**For EACH third-party library identified, you MUST complete ALL of the following steps. Do not skip any.**

### Step 2.1: Fetch Official Documentation

Use `fetch_webpage` or `mcp_tavily_tavily_extract` to retrieve official docs.

**Common Documentation URLs:**

### This Project's Stack (Priority)

| Library | Documentation URL | Used For |
|---------|-------------------|----------|
| React 18 | `https://react.dev/reference/react` | UI framework |
| React Router v7 | `https://reactrouter.com/home` | Client-side routing |
| TanStack Query v5 | `https://tanstack.com/query/latest/docs/framework/react/overview` | Server state, caching |
| Clerk React | `https://clerk.com/docs/quickstarts/react` | Authentication |
| Tailwind CSS v4 | `https://tailwindcss.com/docs` | Styling |
| Vite | `https://vite.dev/guide/` | Build tool, dev server |
| Vitest | `https://vitest.dev/guide/` | Unit testing |
| Testing Library | `https://testing-library.com/docs/react-testing-library/intro/` | Component testing |

### Other Common Libraries

| Library | Documentation URL |
|---------|-------------------|
| React DOM | `https://react.dev/reference/react-dom` |
| TanStack Router | `https://tanstack.com/router/latest` |
| Zustand | `https://docs.pmnd.rs/zustand/getting-started/introduction` |
| Jotai | `https://jotai.org/docs/introduction` |
| Zod | `https://zod.dev/` |
| React Hook Form | `https://react-hook-form.com/docs` |
| Axios | `https://axios-http.com/docs/intro` |
| shadcn/ui | `https://ui.shadcn.com/docs` |
| Radix UI | `https://www.radix-ui.com/primitives/docs/overview/introduction` |
| Framer Motion | `https://www.framer.com/motion/` |
| date-fns | `https://date-fns.org/docs/Getting-Started` |

**For each library, fetch the SPECIFIC documentation page for the feature being used:**

```markdown
### Documentation Fetched

| Library Feature | URL Fetched | Key Findings |
|-----------------|-------------|--------------|
| `useQuery` options | https://tanstack.com/query/latest/docs/framework/react/reference/useQuery | ... |
| `z.object` schema | https://zod.dev/?id=objects | ... |
```

### Step 2.2: Search Best Practices (MANDATORY)

Use `mcp_tavily_tavily_search` to find best practices and pitfalls.

**Required searches for each library:**

```
"[library name] best practices 2024"
"[library name] common mistakes"
"[library name] [specific feature] gotchas"
"[library name] performance tips"
```

**Example for React Query:**
```
"react query useQuery best practices"
"tanstack query staleTime vs gcTime"
"react query infinite loop common mistakes"
```

**Document findings:**

```markdown
### Best Practices Research

| Search Query | Source | Key Finding |
|--------------|--------|-------------|
| "react query useQuery best practices" | TkDodo Blog | Always set staleTime for static data |
```

### Step 2.3: Audit Codebase Usage

Use `list_code_usages` and `grep_search` to find ALL usages of the library/function in the codebase.

```markdown
### Codebase Usage Audit

| Function/Hook | File | Line | Usage Pattern | Matches Best Practice? |
|---------------|------|------|---------------|------------------------|
| `useQuery` | useUser.ts | 15 | Fetches user data | ✅ |
| `useQuery` | usePosts.ts | 8 | Missing error boundary | ⚠️ |
```

**Verify consistency:**
- Are all usages following the same pattern?
- Are there any usages that contradict best practices?
- Are the parameters being passed correctly everywhere?

---

## PHASE 3: Library Behavior Analysis (Per Library)

For EACH third-party library, produce this analysis WITH CITATIONS:

```markdown
---

## [N]. `library/hook/component` — Deep Dive

### Official Documentation Summary
> Direct quote or paraphrase from official docs with URL citation.

**Source**: [URL]

### How It Actually Works

| Behavior | Documentation Says | Our Implementation | Match? |
|----------|-------------------|-------------------|--------|
| Option X | "Does Y" (source) | We pass Z | ✅/❌ |
| Edge case A | "Triggers B" (source) | Not handled | ❌ |

### Documented Gotchas & Pitfalls

From official docs and best practice searches:

| Gotcha | Source | Applies to Our Code? | Mitigation |
|--------|--------|---------------------|------------|
| "useEffect runs twice in StrictMode" | React docs | ✅ Yes | Ensure cleanup function |
| "staleTime defaults to 0" | TanStack Query docs | ✅ Yes | Set explicit staleTime |

### Best Practices Checklist

| Practice | Source | Our Code | Status |
|----------|--------|----------|--------|
| Use error boundaries with queries | TkDodo Blog | Not implemented | ⚠️ |
| Memoize callback dependencies | React docs | Done | ✅ |

### Props/Options Deep Dive

| Prop/Option | Type | Required | Default | Our Usage | Correct? |
|-------------|------|----------|---------|-----------|----------|
| `queryKey` | `QueryKey` | Yes | N/A | `['user', userId]` | ✅ |
| `staleTime` | `number` | No | `0` | Not set | ⚠️ |
| `enabled` | `boolean` | No | `true` | `!!userId` | ✅ |

### Return Value Analysis

| Property | Type | Our Handling | Correct? |
|----------|------|--------------|----------|
| `data` | `TData \| undefined` | Optional chaining | ✅ |
| `error` | `Error \| null` | Not displayed to user | ⚠️ |
| `isLoading` | `boolean` | Shows spinner | ✅ |

### Error Handling

| Error Type | When Thrown | Our Handling | Recommendation |
|------------|-------------|--------------|----------------|
| Network error | Fetch fails | Retries 3x (default) | Consider custom retry |
| 4xx response | Server rejects | Not differentiated | Handle 401 specially |
```

---

## PHASE 4: Cross-Reference Verification

### Step 4.1: Type Verification

If the code uses TypeScript, READ type definitions and verify:

```markdown
### Type Verification

| Code Reference | Expected Type | Actual Type | Match? |
|----------------|---------------|-------------|--------|
| `useQuery<User>` return | `UseQueryResult<User>` | Matches | ✅ |
| `onSubmit` handler | `(data: FormData) => void` | `(data: any) => void` | ❌ |
```

### Step 4.2: Component/Hook Consumer Verification

Find all consumers of components/hooks in this file and verify correct usage:

```markdown
### Consumer Analysis

| Consumer | File | Correct Props? | Handles Loading? | Handles Error? |
|----------|------|----------------|------------------|----------------|
| `<UserProfile />` | Dashboard.tsx | ✅ | ✅ | ❌ Missing |
| `useUserData()` | Settings.tsx | ✅ | ⚠️ No skeleton | ✅ |
```

### Step 4.3: Dependency Array Verification

For hooks with dependency arrays, verify correctness:

```markdown
### Dependency Array Audit

| Hook | Location | Dependencies | ESLint Warning? | Correct? |
|------|----------|--------------|-----------------|----------|
| `useEffect` | Line 45 | `[userId]` | None | ✅ |
| `useCallback` | Line 62 | `[]` | Missing `onSave` | ❌ |
| `useMemo` | Line 78 | `[items]` | None | ✅ |
```

---

## PHASE 5: Implementation Review

### Comprehensive Checklist

| Category | Check | Status | Evidence/Citation |
|----------|-------|--------|-------------------|
| **Library Usage** | Matches documented API | ✅/❌ | Doc URL + line number |
| **Library Usage** | Handles documented edge cases | ✅/❌ | Doc URL + line number |
| **Library Usage** | Follows best practices from search | ✅/❌ | Source URL |
| **React Patterns** | Hooks called at top level | ✅/❌ | |
| **React Patterns** | No hooks in conditionals/loops | ✅/❌ | |
| **React Patterns** | Keys on list items | ✅/❌ | |
| **React Patterns** | Proper cleanup in useEffect | ✅/❌ | |
| **TypeScript** | No `any` types | ✅/❌ | |
| **TypeScript** | Proper generic usage | ✅/❌ | |
| **TypeScript** | Strict null checks handled | ✅/❌ | |
| **Performance** | Proper memoization | ✅/❌ | |
| **Performance** | No unnecessary re-renders | ✅/❌ | |
| **Performance** | Lazy loading where appropriate | ✅/❌ | |
| **Accessibility** | ARIA attributes present | ✅/❌ | |
| **Accessibility** | Keyboard navigation works | ✅/❌ | |
| **Error Handling** | Error boundaries in place | ✅/❌ | |
| **Error Handling** | User-friendly error messages | ✅/❌ | |
| **Imports** | No unused imports | ✅/❌ | |
| **Imports** | No circular dependencies | ✅/❌ | |

### Issues Found

For each issue, provide:

```markdown
### Issue [N]: [Title]

**Severity**: 🔴 Critical / 🟠 Medium / 🟡 Low

**Location**: `file.tsx` line X

**Problem**:
Description of what's wrong.

**Evidence**:
> Quote from documentation or best practice source proving this is an issue.

**Source**: [URL]

**Impact**:
What could go wrong in production (UX, performance, security).

**Recommended Fix**:
```typescript
// corrected code
```
```

---

## PHASE 6: Suggested Fixes

Provide complete, tested fixes for all issues found:

```markdown
## Suggested Fixes

### Fix [N]: [Title]

**Issue Reference**: Issue [N] above

**Before** (`file.tsx` line X):
```typescript
// exact code from file
```

**After**:
```typescript
// corrected code with explanation comments
```

**Why This Fix**:
- Cite documentation: "According to [source], ..."
- Cite best practice: "The recommended pattern from [source] is ..."

**Testing**:
- How to verify this fix works
- Edge cases to test
- Browser/device considerations
```

---

## Frontend-Specific Deep Dive Checklists

> **Note**: Basic standards are in `.github/instructions/vite.instructions.md`. These checklists are for **deep verification during reviews**—fetch docs and compare actual behavior.

### React 18 Hooks (Verify Against Docs)

Fetch: `https://react.dev/reference/react/hooks`

- [ ] `useState` - Initial value correct type, setter used correctly
- [ ] `useEffect` - Cleanup function returns, dependencies correct
- [ ] `useCallback` - All dependencies listed, not over-memoizing
- [ ] `useMemo` - Expensive computation justified, dependencies correct
- [ ] `useRef` - Not used for derived state, `.current` accessed correctly
- [ ] `useContext` - Provider exists in tree, default value appropriate
- [ ] `lazy()` + `Suspense` - Proper fallback UI, error boundary nearby
- [ ] Custom hooks - Follows `use` prefix convention, composable

### TanStack Query v5 (Verify Against Docs)

Fetch: `https://tanstack.com/query/latest/docs/framework/react/overview`

- [ ] `queryKey` is unique and includes all variables (e.g., `['topic', phaseSlug, topicSlug]`)
- [ ] `staleTime` set appropriately (not relying on default 0)
- [ ] `gcTime` (formerly cacheTime) considered for memory
- [ ] `enabled` used for conditional fetching (e.g., `enabled: !!userId`)
- [ ] `select` used for data transformation (not in render)
- [ ] Error handling with `onError` or error boundaries
- [ ] Loading states handled (`isLoading` vs `isPending` vs `isFetching`)
- [ ] Mutations use `useMutation` with proper `invalidateQueries`
- [ ] Optimistic updates use `onMutate` correctly
- [ ] `useQueryClient()` for manual invalidation

### Clerk React (Verify Against Docs)

Fetch: `https://clerk.com/docs/quickstarts/react`

- [ ] `<ClerkProvider>` wraps app with correct `publishableKey`
- [ ] `useAuth()` for `getToken`, `isSignedIn`, `userId`
- [ ] `useUser()` for user profile data
- [ ] `<SignedIn>` / `<SignedOut>` for conditional rendering
- [ ] `<RedirectToSignIn>` for protected routes
- [ ] Token passed to API calls via `getToken()`
- [ ] Appearance customization via `appearance` prop

### React Router v7 (Verify Against Docs)

Fetch: `https://reactrouter.com/home`

- [ ] `<Routes>` and `<Route>` structure correct
- [ ] Dynamic params with `useParams()` typed correctly
- [ ] Navigation with `useNavigate()` or `<Link>`
- [ ] Protected routes pattern implemented correctly
- [ ] Route order: specific routes before dynamic `/:param` routes
- [ ] `<Outlet>` for nested layouts (if used)
- [ ] Error boundaries with `errorElement` (if using data APIs)

### Tailwind CSS v4 (Verify Against Docs)

Fetch: `https://tailwindcss.com/docs`

- [ ] PostCSS config includes `@tailwindcss/postcss`
- [ ] Dark mode classes (`dark:`) used correctly
- [ ] Responsive prefixes (`sm:`, `md:`, `lg:`) in correct order
- [ ] Custom colors/spacing via CSS variables or config
- [ ] No conflicting utility classes
- [ ] Proper use of `@apply` (sparingly, in CSS files)

### Vite/Build (Verify Against Docs)

Fetch: `https://vite.dev/guide/`

- [ ] Environment variables use `import.meta.env.VITE_*`
- [ ] Dynamic imports with `lazy()` for code splitting
- [ ] Assets imported correctly (not string paths)
- [ ] Path aliases (`@/`) configured in `tsconfig.json` and `vite.config.ts`
- [ ] No Node.js APIs in browser code

### Vitest/Testing Library (Verify Against Docs)

Fetch: `https://vitest.dev/guide/` and `https://testing-library.com/docs/react-testing-library/intro/`

- [ ] Tests use `describe`, `it`, `expect` from Vitest
- [ ] Component tests use `render`, `screen` from Testing Library
- [ ] User interactions via `@testing-library/user-event`
- [ ] Async operations with `waitFor` or `findBy*` queries
- [ ] Mocking with `vi.mock()` and `vi.fn()`
- [ ] Query providers wrapped in tests (TanStack Query, Clerk)

---

## Output Format Requirements

1. **Every claim about library behavior MUST have a citation** (URL or "Official docs")
2. **Use tables extensively** for structured comparisons
3. **Code blocks** with `typescript` or `tsx` syntax highlighting
4. **Emoji severity indicators**: 🔴 Critical, 🟠 Medium, 🟡 Low, ✅ Good, ❌ Issue, ⚠️ Warning
5. **Numbered sections** for each library deep dive
6. **Link to source files** using markdown links with line numbers

---

## Execution Strategy

### For Files with 3+ Third-Party Libraries

Consider using `runSubagent` to parallelize research:

```
Spawn a subagent to research [Library X]:
1. Fetch official docs for [specific feature]
2. Search for "[library] [feature] best practices"
3. Search for "[library] [feature] common mistakes"
4. Return: documented behavior, gotchas, best practices with URLs
```

### Research Order

1. **First**: Fetch all official documentation pages (can be parallel)
2. **Second**: Run all best practice searches (can be parallel)
3. **Third**: Audit codebase usages (sequential)
4. **Fourth**: Cross-reference and verify (sequential)
5. **Fifth**: Compile findings and fixes

---

## Example Trigger Phrases

- "review file"
- "review this file"
- "analyze this TypeScript file"
- "deep dive into this component"
- "check the hooks in this file"
- "audit this implementation"
- "review this React component"
