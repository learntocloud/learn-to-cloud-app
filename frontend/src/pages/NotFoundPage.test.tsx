/**
 * Tests for NotFoundPage component.
 * Tests 404 page rendering and navigation.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '../test/test-utils';
import { NotFoundPage } from './NotFoundPage';

describe('NotFoundPage', () => {
  it('renders 404 heading', () => {
    render(<NotFoundPage />);

    expect(screen.getByRole('heading', { name: '404' })).toBeInTheDocument();
  });

  it('renders error message', () => {
    render(<NotFoundPage />);

    expect(screen.getByText(/page you're looking for doesn't exist/i)).toBeInTheDocument();
  });

  it('renders Go Home link', () => {
    render(<NotFoundPage />);

    const homeLink = screen.getByRole('link', { name: /return to homepage/i });
    expect(homeLink).toBeInTheDocument();
    expect(homeLink).toHaveAttribute('href', '/');
  });

  it('has main landmark with proper role', () => {
    render(<NotFoundPage />);

    const main = screen.getByRole('main');
    expect(main).toBeInTheDocument();
  });

  it('sets document title', () => {
    render(<NotFoundPage />);

    // The useEffect should set the document title
    expect(document.title).toContain('404');
  });
});
