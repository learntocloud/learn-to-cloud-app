/**
 * Unit tests for components/phase-badge-data.ts
 *
 * Tests the PHASE_BADGE_DATA to ensure all phases have proper badge configuration.
 *
 * Total test cases: 6
 * - TestPhaseBadgeData: 6 tests
 */

import { describe, it, expect } from 'vitest';
import { PHASE_BADGE_DATA } from './phase-badge-data';

describe('TestPhaseBadgeData', () => {
  it('should have badge data for all 7 phases (0-6)', () => {
    expect(Object.keys(PHASE_BADGE_DATA)).toHaveLength(7);

    for (let i = 0; i < 7; i++) {
      expect(PHASE_BADGE_DATA).toHaveProperty(i.toString());
    }
  });

  it('should have all required properties for each badge', () => {
    Object.entries(PHASE_BADGE_DATA).forEach(([_phaseId, badge]) => {
      expect(badge).toHaveProperty('name');
      expect(badge).toHaveProperty('icon');
      expect(badge).toHaveProperty('phaseName');

      expect(typeof badge.name).toBe('string');
      expect(typeof badge.icon).toBe('string');
      expect(typeof badge.phaseName).toBe('string');

      expect(badge.name.length).toBeGreaterThan(0);
      expect(badge.icon.length).toBeGreaterThan(0);
      expect(badge.phaseName.length).toBeGreaterThan(0);
    });
  });

  it('should have unique badge names', () => {
    const names = Object.values(PHASE_BADGE_DATA).map((b) => b.name);
    const uniqueNames = new Set(names);
    expect(uniqueNames.size).toBe(names.length);
  });

  it('should have unique badge icons', () => {
    const icons = Object.values(PHASE_BADGE_DATA).map((b) => b.icon);
    const uniqueIcons = new Set(icons);
    expect(uniqueIcons.size).toBe(icons.length);
  });

  it('should have unique phase names', () => {
    const phaseNames = Object.values(PHASE_BADGE_DATA).map((b) => b.phaseName);
    const uniquePhaseNames = new Set(phaseNames);
    expect(uniquePhaseNames.size).toBe(phaseNames.length);
  });

  it('should have expected badge names for each phase', () => {
    const expectedNames = {
      0: 'Cloud Seedling',
      1: 'Terminal Ninja',
      2: 'Code Crafter',
      3: 'AI Apprentice',
      4: 'Cloud Explorer',
      5: 'DevOps Rocketeer',
      6: 'Security Guardian',
    };

    Object.entries(expectedNames).forEach(([phaseId, expectedName]) => {
      expect(PHASE_BADGE_DATA[Number(phaseId)].name).toBe(expectedName);
    });
  });
});
