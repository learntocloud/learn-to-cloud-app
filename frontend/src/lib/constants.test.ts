/**
 * Unit tests for lib/constants.ts
 *
 * Tests application constants to ensure they match expected values
 * and maintain consistency across the application.
 *
 * Total test cases: 8
 * - TestQuestionAnswerLimits: 2 tests
 * - TestBadgeConfiguration: 6 tests
 */

import { describe, it, expect } from 'vitest';
import {
  QUESTION_ANSWER_MAX_CHARS,
  QUESTION_ANSWER_MIN_CHARS,
  TOTAL_BADGES,
  ALL_BADGES,
} from './constants';

describe('TestQuestionAnswerLimits', () => {
  it('should have minimum character limit of 10', () => {
    expect(QUESTION_ANSWER_MIN_CHARS).toBe(10);
  });

  it('should have maximum character limit of 512', () => {
    expect(QUESTION_ANSWER_MAX_CHARS).toBe(512);
  });
});

describe('TestBadgeConfiguration', () => {
  it('should have total of 10 badges', () => {
    expect(TOTAL_BADGES).toBe(10);
    expect(ALL_BADGES).toHaveLength(10);
  });

  it('should have 7 phase badges', () => {
    const phaseBadges = ALL_BADGES.filter((b) => b.id.startsWith('phase_'));
    expect(phaseBadges).toHaveLength(7);
  });

  it('should have 3 streak badges', () => {
    const streakBadges = ALL_BADGES.filter((b) => b.id.startsWith('streak_'));
    expect(streakBadges).toHaveLength(3);
  });

  it('should have unique badge IDs', () => {
    const ids = ALL_BADGES.map((b) => b.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ALL_BADGES.length);
  });

  it('should have all required badge properties', () => {
    ALL_BADGES.forEach((badge) => {
      expect(badge).toHaveProperty('id');
      expect(badge).toHaveProperty('name');
      expect(badge).toHaveProperty('icon');
      expect(badge).toHaveProperty('num');
      expect(badge).toHaveProperty('howTo');

      expect(typeof badge.id).toBe('string');
      expect(typeof badge.name).toBe('string');
      expect(typeof badge.icon).toBe('string');
      expect(typeof badge.num).toBe('string');
      expect(typeof badge.howTo).toBe('string');
    });
  });

  it('should have sequential badge numbers starting from #001', () => {
    const expectedNums = Array.from({ length: 10 }, (_, i) =>
      `#${String(i + 1).padStart(3, '0')}`
    );

    const actualNums = ALL_BADGES.map((b) => b.num);
    expect(actualNums).toEqual(expectedNums);
  });
});
