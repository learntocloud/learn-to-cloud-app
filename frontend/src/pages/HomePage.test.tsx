/**
 * Tests for HomePage component.
 * Tests hero section, phase timeline, and CTA buttons.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '../test/test-utils';
import { HomePage } from './HomePage';

// Mock Clerk hooks - needs to return UserResource compatible types
vi.mock('@clerk/clerk-react', () => ({
  useUser: vi.fn(() => ({
    isSignedIn: false,
    isLoaded: true,
    user: null,
  })),
  SignUpButton: ({ children }: { children: React.ReactNode }) => children,
}));

// Access the mocked useUser
import { useUser } from '@clerk/clerk-react';
const mockedUseUser = vi.mocked(useUser);

describe('HomePage', () => {
  beforeEach(() => {
    mockedUseUser.mockReturnValue({
      isSignedIn: false,
      isLoaded: true,
      user: null,
    } as ReturnType<typeof useUser>);
  });

  it('renders hero section', () => {
    render(<HomePage />);

    // Should show the tagline
    expect(screen.getByText(/free, open-source guide/i)).toBeInTheDocument();
  });

  it('renders Learn to Cloud logo', () => {
    render(<HomePage />);

    const logo = screen.getByAltText(/learn to cloud/i);
    expect(logo).toBeInTheDocument();
  });

  it('renders phase timeline', () => {
    render(<HomePage />);

    // Check for phase names
    expect(screen.getByText('Starting from Zero')).toBeInTheDocument();
    expect(screen.getByText('Linux and Bash')).toBeInTheDocument();
    expect(screen.getByText('Programming Fundamentals')).toBeInTheDocument();
  });

  it('renders all 7 phases', () => {
    render(<HomePage />);

    // Phase numbers 0-6
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
  });

  it('renders why section cards', () => {
    render(<HomePage />);

    expect(screen.getByText('Hands-On Focused')).toBeInTheDocument();
    expect(screen.getByText('Community Driven')).toBeInTheDocument();
    expect(screen.getByText('100% Free & Open Source')).toBeInTheDocument();
  });

  it('shows Get Started button when signed out', () => {
    render(<HomePage />);

    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument();
  });

  it('shows View Curriculum link when signed out', () => {
    render(<HomePage />);

    // The link has aria-label "Browse the learning curriculum"
    const curriculumLink = screen.getByRole('link', { name: /browse the learning curriculum/i });
    expect(curriculumLink).toBeInTheDocument();
    expect(curriculumLink).toHaveAttribute('href', '/phases');
  });

  it('sets document title', () => {
    render(<HomePage />);

    expect(document.title).toContain('Learn to Cloud');
  });
});

describe('HomePage - Authenticated', () => {
  beforeEach(() => {
    mockedUseUser.mockReturnValue({
      isSignedIn: true,
      isLoaded: true,
      user: { id: 'user_123' },
    } as ReturnType<typeof useUser>);
  });

  it('shows Go to Dashboard button when signed in', () => {
    render(<HomePage />);

    // The button has aria-label "Go to your dashboard"
    expect(screen.getByRole('button', { name: /go to your dashboard/i })).toBeInTheDocument();
  });
});

describe('HomePage - Loading State', () => {
  beforeEach(() => {
    mockedUseUser.mockReturnValue({
      isSignedIn: false,
      isLoaded: false,
      user: null,
    } as ReturnType<typeof useUser>);
  });

  it('shows loading state while user status is loading', () => {
    render(<HomePage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
