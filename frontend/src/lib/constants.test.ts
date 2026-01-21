/**
 * Tests for constants module.
 * Validates badge definitions and configuration values.
 */

import { describe, it, expect } from 'vitest';
import {
  QUESTION_ANSWER_MAX_CHARS,
  QUESTION_ANSWER_MIN_CHARS,
  TOTAL_BADGES,
  PHASE_BADGES,
  STREAK_BADGES,
  ALL_BADGES,
} from './constants';

describe('Question Answer Constants', () => {
  it('has valid min/max character limits', () => {
    expect(QUESTION_ANSWER_MIN_CHARS).toBeGreaterThan(0);
    expect(QUESTION_ANSWER_MAX_CHARS).toBeGreaterThan(QUESTION_ANSWER_MIN_CHARS);
  });

  it('max chars is reasonable for short answers', () => {
    expect(QUESTION_ANSWER_MAX_CHARS).toBeLessThanOrEqual(1000);
  });

  it('min chars enforces thoughtful answers', () => {
    expect(QUESTION_ANSWER_MIN_CHARS).toBeGreaterThanOrEqual(10);
  });
});

describe('Badge Definitions', () => {
  it('TOTAL_BADGES matches actual badge count', () => {
    expect(ALL_BADGES.length).toBe(TOTAL_BADGES);
  });

  it('all phase badges have required fields', () => {
    PHASE_BADGES.forEach((badge) => {
      expect(badge.id).toBeDefined();
      expect(badge.name).toBeDefined();
      expect(badge.icon).toBeDefined();
      expect(badge.num).toBeDefined();
      expect(badge.howTo).toBeDefined();
      expect(badge.phaseName).toBeDefined();
    });
  });

  it('all streak badges have required fields', () => {
    STREAK_BADGES.forEach((badge) => {
      expect(badge.id).toBeDefined();
      expect(badge.name).toBeDefined();
      expect(badge.icon).toBeDefined();
      expect(badge.num).toBeDefined();
      expect(badge.howTo).toBeDefined();
    });
  });

  it('phase badges have unique IDs', () => {
    const ids = PHASE_BADGES.map((b) => b.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it('streak badges have unique IDs', () => {
    const ids = STREAK_BADGES.map((b) => b.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it('all badges have unique IDs across types', () => {
    const ids = ALL_BADGES.map((b) => b.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it('phase badges have correct phase ID format', () => {
    PHASE_BADGES.forEach((badge) => {
      expect(badge.id).toMatch(/^phase_\d+_complete$/);
    });
  });

  it('streak badges have correct streak ID format', () => {
    STREAK_BADGES.forEach((badge) => {
      expect(badge.id).toMatch(/^streak_\d+$/);
    });
  });

  it('badge numbers are formatted correctly', () => {
    ALL_BADGES.forEach((badge) => {
      expect(badge.num).toMatch(/^#\d{3}$/);
    });
  });

  it('has expected number of phase badges (7 phases)', () => {
    expect(PHASE_BADGES.length).toBe(7);
  });

  it('has expected number of streak badges (3 milestones)', () => {
    expect(STREAK_BADGES.length).toBe(3);
  });

  it('streak badges are for 7, 30, and 100 days', () => {
    const streakDays = STREAK_BADGES.map((b) => parseInt(b.id.replace('streak_', '')));
    expect(streakDays).toContain(7);
    expect(streakDays).toContain(30);
    expect(streakDays).toContain(100);
  });
});
