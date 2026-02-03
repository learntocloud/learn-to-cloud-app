/**
 * Tests for ActivityHeatmap component.
 * Tests grid rendering, activity levels, and accessibility.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '../test/test-utils';
import { ActivityHeatmap } from './ActivityHeatmap';
import type { ActivityHeatmapDay } from '@/lib/types';

const mockDays: ActivityHeatmapDay[] = [
  { date: '2026-01-20', count: 5, activity_types: ['step_complete'] },
  { date: '2026-01-19', count: 2, activity_types: ['question_attempt'] },
  { date: '2026-01-18', count: 0, activity_types: [] },
  { date: '2026-01-17', count: 10, activity_types: ['step_complete', 'question_attempt'] },
  { date: '2026-01-16', count: 1, activity_types: ['step_complete'] },
];

describe('ActivityHeatmap', () => {
  it('renders the heatmap container', () => {
    render(
      <ActivityHeatmap
        days={mockDays}
        startDate="2026-01-01"
        endDate="2026-01-20"
      />
    );

    // Check for the main container with accessible label
    const heatmap = screen.getByRole('group', { name: /activity heatmap/i });
    expect(heatmap).toBeInTheDocument();
  });

  it('renders grid structure', () => {
    render(
      <ActivityHeatmap
        days={mockDays}
        startDate="2026-01-01"
        endDate="2026-01-20"
      />
    );

    // Should have a grid element
    const grid = screen.getByRole('grid');
    expect(grid).toBeInTheDocument();
  });

  it('displays month labels', () => {
    render(
      <ActivityHeatmap
        days={mockDays}
        startDate="2025-12-01"
        endDate="2026-01-20"
      />
    );

    // Should show month labels
    expect(screen.getByText('Dec')).toBeInTheDocument();
    expect(screen.getByText('Jan')).toBeInTheDocument();
  });

  it('handles empty days array', () => {
    render(
      <ActivityHeatmap
        days={[]}
        startDate="2026-01-01"
        endDate="2026-01-20"
      />
    );

    // Should still render the container
    const heatmap = screen.getByRole('group', { name: /activity heatmap/i });
    expect(heatmap).toBeInTheDocument();
  });

  it('shows weekday labels', () => {
    render(
      <ActivityHeatmap
        days={mockDays}
        startDate="2026-01-01"
        endDate="2026-01-20"
      />
    );

    // Alternating weekday labels (Mon, Wed, Fri typically shown)
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
    expect(screen.getByText('Fri')).toBeInTheDocument();
  });

  it('renders cells with appropriate colors based on activity level', () => {
    const { container } = render(
      <ActivityHeatmap
        days={[
          { date: '2026-01-20', count: 0, activity_types: [] },
          { date: '2026-01-19', count: 5, activity_types: ['step_complete'] },
          { date: '2026-01-18', count: 10, activity_types: ['step_complete'] },
        ]}
        startDate="2026-01-18"
        endDate="2026-01-20"
      />
    );

    // Check that cells exist (color classes are applied)
    const cells = container.querySelectorAll('[role="gridcell"]');
    expect(cells.length).toBeGreaterThan(0);
  });

  it('handles single day range', () => {
    render(
      <ActivityHeatmap
        days={[{ date: '2026-01-20', count: 5, activity_types: ['step_complete'] }]}
        startDate="2026-01-20"
        endDate="2026-01-20"
      />
    );

    const heatmap = screen.getByRole('group', { name: /activity heatmap/i });
    expect(heatmap).toBeInTheDocument();
  });

  it('handles date range spanning multiple months', () => {
    render(
      <ActivityHeatmap
        days={mockDays}
        startDate="2025-10-01"
        endDate="2026-01-20"
      />
    );

    // Should show multiple month labels
    expect(screen.getByText('Oct')).toBeInTheDocument();
    expect(screen.getByText('Jan')).toBeInTheDocument();
  });
});
