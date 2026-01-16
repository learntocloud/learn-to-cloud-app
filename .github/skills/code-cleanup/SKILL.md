---
name: code-cleanup
description: Find and remove unused/dead code from the codebase. Use when auditing for unused imports, finding dead API methods, removing duplicate files, or doing a code cleanup pass.
---

# Frontend Code Review Guidelines

## Codebase Philosophy (v0 - Clean Foundation)

**CRITICAL**: This codebase is version 0 - a clean foundation with NO legacy code and NO future planned features to preserve.

### Frontend Architecture Principle

**The frontend is 100% static.** It has NO business logic - it only:
- Renders UI components
- Calls the API for all data and operations
- Displays responses from the API

All logic, calculations, validation, and business rules live in the **API only**. The frontend is a thin presentation layer.

### Code Review Rules

When reviewing frontend code:
- **Remove ALL unused code** - No "might be needed later" exceptions
- **Remove ALL dead code** - If it's not called, delete it
- **No legacy considerations** - This is a fresh start, not a migration
- **No future feature preservation** - We build what we need when we need it
- **No business logic in frontend** - If it's not UI rendering or API calls, it doesn't belong

## What to Look For

### 1. Unused Files
- Components that are never imported
- Duplicate files (PascalCase vs kebab-case naming)
- Utility files with no consumers

### 2. Unused Exports
- Functions/hooks exported but never called
- Types exported but never imported
- Constants exported but never used

### 3. Unused Imports
- Import statements for things not used in the file
- Type imports for types not referenced

### 4. Dead API Methods
- API client methods that have no callers
- Associated types only used by dead methods

### 5. Duplicate Code
- Same component with different file naming conventions
- Types defined in multiple places
- Similar functionality implemented twice

### 6. Business Logic in Frontend (Should Not Exist)
- Data transformations that should be in API
- Calculations or derived values
- Validation logic beyond basic form UX
- State management for business rules
- Any "smart" logic - frontend should be "dumb"

## Review Process

1. **List all files** in the target directory
2. **For each exported item**, search for imports/usages
3. **If no external usage found**, mark for removal
4. **Verify build passes** after each removal batch
5. **Run tests** to ensure nothing broke

## Verification Commands

```bash
# Check for unused exports with grep
grep -r "functionName" src/ | grep -v "definition-file.ts"

# Find all imports of a module
grep -r "from.*module-name" src/

# TypeScript build check
npm run build

# ESLint for unused imports
npx eslint src/ --ext .ts,.tsx
```

## Don't Preserve Code For

- ❌ "Future features" - Build when needed
- ❌ "API completeness" - Only implement what's used
- ❌ "It might break something" - Tests will catch it
- ❌ "Legacy compatibility" - This is v0, no legacy

## Do Preserve Code For

- ✅ Active features in the UI
- ✅ Internal helper functions called by other code
- ✅ Types used by active code paths
- ✅ Shared utilities with multiple consumers
