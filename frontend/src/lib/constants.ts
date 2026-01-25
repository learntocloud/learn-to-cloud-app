/**
 * Application-wide constants.
 * Centralizes magic numbers and configuration values for maintainability.
 */

export const QUESTION_ANSWER_MAX_CHARS = 2000;
export const QUESTION_ANSWER_MIN_CHARS = 10;
export const TOTAL_BADGES = 10;

/**
 * Phase badge definitions with display names for celebrations.
 * Single source of truth for frontend badge metadata.
 */
export const PHASE_BADGES = [
  { id: 'phase_0_complete', name: 'Cloud Seedling', icon: '🌱', num: '#001', howTo: 'Complete Phase 0: Starting from Zero', phaseName: 'IT Fundamentals & Cloud Overview' },
  { id: 'phase_1_complete', name: 'Terminal Ninja', icon: '🐧', num: '#002', howTo: 'Complete Phase 1: Linux and Bash', phaseName: 'Command Line, Version Control & Infrastructure Basics' },
  { id: 'phase_2_complete', name: 'Code Crafter', icon: '🐍', num: '#003', howTo: 'Complete Phase 2: Programming Fundamentals', phaseName: 'Python, FastAPI, Databases & AI Integration' },
  { id: 'phase_3_complete', name: 'AI Apprentice', icon: '🤖', num: '#004', howTo: 'Complete Phase 3: AI Tools & Intentional Learning', phaseName: 'Prompt Engineering, GitHub Copilot & AI Tools' },
  { id: 'phase_4_complete', name: 'Cloud Explorer', icon: '☁️', num: '#005', howTo: 'Complete Phase 4: Cloud Platform Fundamentals', phaseName: 'VMs, Networking, Security & Deployment' },
  { id: 'phase_5_complete', name: 'DevOps Rocketeer', icon: '🚀', num: '#006', howTo: 'Complete Phase 5: DevOps Fundamentals', phaseName: 'Docker, CI/CD, Kubernetes & Monitoring' },
  { id: 'phase_6_complete', name: 'Security Guardian', icon: '🔐', num: '#007', howTo: 'Complete Phase 6: Securing Your Cloud Applications', phaseName: 'IAM, Data Protection & Threat Detection' },
] as const;

export const STREAK_BADGES = [
  { id: 'streak_7', name: 'Week Warrior', icon: '🔥', num: '#008', howTo: 'Maintain a 7-day learning streak' },
  { id: 'streak_30', name: 'Monthly Master', icon: '💪', num: '#009', howTo: 'Maintain a 30-day learning streak' },
  { id: 'streak_100', name: 'Century Club', icon: '💯', num: '#010', howTo: 'Maintain a 100-day learning streak' },
] as const;

/** All badges for Pokédex-style collection UI. */
export const ALL_BADGES = [...PHASE_BADGES, ...STREAK_BADGES] as const;
