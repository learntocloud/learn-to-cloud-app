---
applyTo: 'frontend/**/*.{ts,tsx,js,jsx}'
---

# Frontend Architecture

## Core Principle: The Frontend is a Thin Presentation Layer

**The frontend has NO business logic.** It only:
- Renders UI components
- Calls the API for all data and operations
- Displays responses from the API

All logic, calculations, validation, and business rules live in the **API only**.

## What Belongs in Frontend

✅ UI components and styling
✅ API client calls (`lib/api.ts`)
✅ Form state and basic UX validation (e.g., "field required")
✅ Routing and navigation
✅ Loading/error states

## What Does NOT Belong in Frontend

❌ Business logic or calculations
❌ Data transformations beyond display formatting
❌ Validation rules (beyond basic UX)
❌ Derived state from business rules
❌ Any "smart" logic - frontend should be "dumb"

## Code Quality

- Remove unused imports, components, and exports
- No "might be needed later" code - build when needed
- If a function isn't called, delete it
