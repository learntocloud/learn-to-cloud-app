/**
 * Unit tests for components/PhaseCompletionCheck.tsx
 *
 * Tests the PhaseCompletionCheck component to ensure it properly detects
 * phase completion and shows celebration modals.
 *
 * Total test cases: 8
 * - TestPhaseCompletionCheck: 8 tests
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PhaseCompletionCheck } from './PhaseCompletionCheck';
import { setupLocalStorageMock } from '../test/test-utils';

// Mock PhaseCelebrationModal
vi.mock('./PhaseCelebrationModal', () => ({
  PhaseCelebrationModal: ({
    isOpen,
    phaseNumber,
  }: {
    isOpen: boolean;
    phaseNumber: number;
  }) => {
    if (!isOpen) return null;
    return <div data-testid="celebration-modal">Phase {phaseNumber} Celebration</div>;
  },
}));

describe('TestPhaseCompletionCheck', () => {
  beforeEach(() => {
    setupLocalStorageMock();
    localStorage.clear();
  });

  const earnedBadges = [
    { id: 'phase_0_complete', name: 'Cloud Seedling', icon: '🌱' },
    { id: 'streak_7', name: 'Week Warrior', icon: '🔥' },
  ];

  it('should show celebration modal when badge is earned and not previously celebrated', async () => {
    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('celebration-modal')).toBeInTheDocument();
    });
  });

  it('should not show celebration modal when badge is not earned', () => {
    const noBadges: { id: string; name: string; icon: string }[] = [];

    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={noBadges}
        nextPhaseSlug="phase-1"
      />
    );

    expect(screen.queryByTestId('celebration-modal')).not.toBeInTheDocument();
  });

  it('should not show celebration modal when phase was already celebrated', async () => {
    // Mark phase 0 as already celebrated
    localStorage.setItem('ltc_celebrated_phases', JSON.stringify([0]));

    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    await waitFor(() => {
      expect(screen.queryByTestId('celebration-modal')).not.toBeInTheDocument();
    });
  });

  it('should mark phase as celebrated in localStorage', async () => {
    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    await waitFor(() => {
      const stored = localStorage.getItem('ltc_celebrated_phases');
      expect(stored).toBeTruthy();
      const celebrated = JSON.parse(stored!);
      expect(celebrated).toContain(0);
    });
  });

  it('should not show celebration for different phase when badge ID does not match', () => {
    const phase1Badges = [{ id: 'phase_1_complete', name: 'Terminal Ninja', icon: '🐧' }];

    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={phase1Badges}
        nextPhaseSlug="phase-1"
      />
    );

    expect(screen.queryByTestId('celebration-modal')).not.toBeInTheDocument();
  });

  it('should handle localStorage errors gracefully', async () => {
    // Mock localStorage to throw error
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('localStorage error');
    });

    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    // Should still show modal even if localStorage fails
    await waitFor(() => {
      expect(screen.getByTestId('celebration-modal')).toBeInTheDocument();
    });

    getItemSpy.mockRestore();
  });

  it('should return null when badge data is missing for phase', () => {
    const { container } = render(
      <PhaseCompletionCheck
        phaseNumber={999}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('should preserve multiple celebrated phases in localStorage', async () => {
    // Pre-populate with phase 1 celebrated
    localStorage.setItem('ltc_celebrated_phases', JSON.stringify([1]));

    render(
      <PhaseCompletionCheck
        phaseNumber={0}
        earnedBadges={earnedBadges}
        nextPhaseSlug="phase-1"
      />
    );

    await waitFor(() => {
      const stored = localStorage.getItem('ltc_celebrated_phases');
      const celebrated = JSON.parse(stored!);
      expect(celebrated).toContain(0);
      expect(celebrated).toContain(1);
      expect(celebrated).toHaveLength(2);
    });
  });
});
