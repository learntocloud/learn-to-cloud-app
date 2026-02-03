/**
 * Tests for constants module.
 * Validates configuration values.
 */

import { describe, it, expect } from 'vitest';
import {
  QUESTION_ANSWER_MAX_CHARS,
  QUESTION_ANSWER_MIN_CHARS,
} from './constants';

describe('Question Answer Constants', () => {
  it('has valid min/max character limits', () => {
    expect(QUESTION_ANSWER_MIN_CHARS).toBeGreaterThan(0);
    expect(QUESTION_ANSWER_MAX_CHARS).toBeGreaterThan(QUESTION_ANSWER_MIN_CHARS);
  });

  it('max chars allows thorough answers', () => {
    expect(QUESTION_ANSWER_MAX_CHARS).toBeGreaterThanOrEqual(500);
    expect(QUESTION_ANSWER_MAX_CHARS).toBeLessThanOrEqual(5000);
  });

  it('min chars enforces thoughtful answers', () => {
    expect(QUESTION_ANSWER_MIN_CHARS).toBeGreaterThanOrEqual(10);
  });
});
