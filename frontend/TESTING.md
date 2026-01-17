# Frontend Testing Guide

This guide explains how to run and write tests for the Learn to Cloud frontend.

## 🚀 Quick Start

```bash
cd frontend

# Install dependencies (if not already done)
npm install

# Run all tests
npm test

# Run tests with UI (interactive)
npm run test:ui

# Run tests with coverage report
npm run test:coverage
```

## 📁 Test File Structure

```
frontend/src/
├── test/
│   └── setup.ts                    # Test configuration
├── lib/
│   ├── theme.test.ts              # Theme utilities tests
│   ├── api-client.test.ts         # API client tests
│   └── hooks.test.ts              # (To be added) React Query hooks tests
└── components/
    └── KnowledgeQuestion.test.tsx # Component tests
```

## ✅ Current Test Coverage

### Theme Utilities (`lib/theme.test.ts`)
- ✅ System theme detection
- ✅ localStorage integration
- ✅ Theme application to DOM
- ✅ Event system (onThemeChange)
- ✅ SSR safety (window undefined checks)
- **15 tests covering all theme functionality**

### API Client (`lib/api-client.test.ts`)
- ✅ Authentication header injection
- ✅ Error handling (network failures, HTTP errors)
- ✅ 404 handling (returns null)
- ✅ Request/response transformation
- ✅ Token-less requests (public endpoints)
- **12+ tests covering critical API paths**

### KnowledgeQuestion Component (`components/KnowledgeQuestion.test.tsx`)
- ✅ Rendering states (answered/unanswered)
- ✅ Form validation (min/max characters)
- ✅ User interactions (typing, submitting)
- ✅ Success/failure feedback
- ✅ Loading states
- ✅ Error handling
- **14+ tests covering all component behaviors**

**Total: 40+ tests**

## 🧪 Writing Tests

### Unit Test Example (Pure Functions)

```typescript
// lib/utils.test.ts
import { describe, it, expect } from 'vitest';
import { formatDate } from './utils';

describe('formatDate', () => {
  it('formats ISO date to readable string', () => {
    const result = formatDate('2024-01-15T10:30:00Z');
    expect(result).toBe('January 15, 2024');
  });
});
```

### Component Test Example

```typescript
// components/MyButton.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MyButton } from './MyButton';

describe('MyButton', () => {
  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<MyButton onClick={onClick}>Click me</MyButton>);

    fireEvent.click(screen.getByText('Click me'));

    expect(onClick).toHaveBeenCalledOnce();
  });
});
```

### API Client Test Example

```typescript
// lib/api-client.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createApiClient } from './api-client';

describe('API Client', () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    global.fetch = mockFetch;
  });

  it('fetches data with auth header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data: 'test' }),
    });

    const client = createApiClient(async () => 'token');
    await client.getUserInfo();

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer token',
        }),
      })
    );
  });
});
```

## 🎯 Test Commands

| Command | Description |
|---------|-------------|
| `npm test` | Run all tests in watch mode |
| `npm test -- --run` | Run tests once (CI mode) |
| `npm run test:ui` | Open Vitest UI in browser |
| `npm run test:coverage` | Generate coverage report |
| `npm test -- MyComponent` | Run tests matching "MyComponent" |
| `npm test -- --reporter=verbose` | Detailed test output |

## 📊 Coverage Goals

| File Type | Current | Target |
|-----------|---------|--------|
| Utilities | ~80% | 90% |
| Components | ~40% | 70% |
| Hooks | 0% | 60% |
| Overall | ~35% | 60-70% |

## 🔍 Common Testing Patterns

### Testing React Query Hooks

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDashboard } from './hooks';

it('fetches dashboard data', async () => {
  const queryClient = new QueryClient();
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );

  const { result } = renderHook(() => useDashboard(), { wrapper });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toBeDefined();
});
```

### Testing User Interactions

```typescript
import userEvent from '@testing-library/user-event';

it('handles form submission', async () => {
  const user = userEvent.setup();
  render(<MyForm onSubmit={mockSubmit} />);

  await user.type(screen.getByLabelText('Email'), 'test@example.com');
  await user.click(screen.getByRole('button', { name: /submit/i }));

  expect(mockSubmit).toHaveBeenCalledWith({ email: 'test@example.com' });
});
```

### Testing Async State Changes

```typescript
it('shows loading then success state', async () => {
  render(<AsyncComponent />);

  expect(screen.getByText('Loading...')).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByText('Success!')).toBeInTheDocument();
  });
});
```

## 🐛 Debugging Tests

### VSCode Integration

Add to `.vscode/settings.json`:

```json
{
  "vitest.enable": true,
  "vitest.commandLine": "npm test"
}
```

### Browser Debugging

```typescript
it('debug test', () => {
  const { debug } = render(<MyComponent />);
  debug(); // Prints DOM to console
  screen.debug(); // Alternative
});
```

### Breakpoints

```typescript
it('pauses execution', () => {
  debugger; // Pause here when running with --inspect
  expect(something).toBe(true);
});
```

## 📚 Resources

- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/react)
- [Testing Library Queries](https://testing-library.com/docs/queries/about)
- [Common Mistakes](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)
- [Vitest UI](https://vitest.dev/guide/ui.html)

## ✨ Best Practices

1. **Test behavior, not implementation**
   - ✅ `expect(screen.getByText('Success')).toBeInTheDocument()`
   - ❌ `expect(component.state.isSuccess).toBe(true)`

2. **Use semantic queries**
   - ✅ `screen.getByRole('button', { name: /submit/i })`
   - ❌ `screen.getByTestId('submit-btn')`

3. **Avoid testing library internals**
   - Test what users see and do
   - Don't test React Query cache directly

4. **Keep tests isolated**
   - Each test should be independent
   - Use `beforeEach` for shared setup

5. **Use meaningful test names**
   - ✅ `it('shows error when email is invalid')`
   - ❌ `it('works')`

## 🎓 Next Steps

### Priority Test Files Needed
1. `lib/hooks.test.ts` - React Query hooks
2. `components/TopicContent.test.tsx` - Step completion logic
3. `components/ActivityHeatmap.test.tsx` - Data visualization
4. `lib/api-client.test.ts` - Expand coverage for all endpoints

### E2E Testing (Future)
Consider adding Playwright for:
- User sign-up flow
- Complete a topic end-to-end
- Submit GitHub repository
- Generate certificate

Run `npm run test:coverage` to see what needs testing!
