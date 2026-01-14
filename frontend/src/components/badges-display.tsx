"use client";

import { Badge } from "@/lib/types";

interface BadgesDisplayProps {
  badges: Badge[];
  showEmpty?: boolean;
  compact?: boolean; // Compact mode for inline display
}

// All available badges (for showing locked state)
const ALL_BADGES: Badge[] = [
  // Phase badges (7 phases: 0-6)
  {
    id: "phase_0_complete",
    name: "Cloud Seedling",
    description: "Completed Phase 0: IT Fundamentals",
    icon: "🌱",
  },
  {
    id: "phase_1_complete",
    name: "Terminal Ninja",
    description: "Completed Phase 1: Linux & Bash",
    icon: "🐧",
  },
  {
    id: "phase_2_complete",
    name: "Code Crafter",
    description: "Completed Phase 2: Programming & APIs",
    icon: "🐍",
  },
  {
    id: "phase_3_complete",
    name: "AI Apprentice",
    description: "Completed Phase 3: AI & Productivity",
    icon: "🤖",
  },
  {
    id: "phase_4_complete",
    name: "Cloud Explorer",
    description: "Completed Phase 4: Cloud Deployment",
    icon: "☁️",
  },
  {
    id: "phase_5_complete",
    name: "DevOps Rocketeer",
    description: "Completed Phase 5: DevOps & Containers",
    icon: "🚀",
  },
  {
    id: "phase_6_complete",
    name: "Security Guardian",
    description: "Completed Phase 6: Cloud Security",
    icon: "🔐",
  },
  // Streak badges
  {
    id: "streak_7",
    name: "Week Warrior",
    description: "Maintained a 7-day learning streak",
    icon: "🔥",
  },
  {
    id: "streak_30",
    name: "Monthly Master",
    description: "Maintained a 30-day learning streak",
    icon: "💪",
  },
  {
    id: "streak_100",
    name: "Century Club",
    description: "Maintained a 100-day learning streak",
    icon: "💯",
  },
];

export function BadgesDisplay({ badges, showEmpty = true, compact = false }: BadgesDisplayProps) {
  const earnedIds = new Set(badges.map((b) => b.id));

  // If no badges earned and we don't want to show empty state
  if (badges.length === 0 && !showEmpty) {
    return null;
  }

  // Separate earned and unearned badges
  const earnedBadges = ALL_BADGES.filter((b) => earnedIds.has(b.id));
  const unearnedBadges = ALL_BADGES.filter((b) => !earnedIds.has(b.id));

  if (badges.length === 0) {
    return null;
  }

  return (
    <div>
      {/* Earned badges as horizontal pills */}
      <div className="flex flex-wrap gap-2">
        {earnedBadges.map((badge) => (
          <div
            key={badge.id}
            className={`group relative inline-flex items-center gap-1.5 ${compact ? 'px-2 py-1' : 'px-3 py-1.5'} bg-gray-100 dark:bg-gray-800 rounded-full text-sm`}
            title={badge.description}
          >
            <span role="img" aria-label={badge.name}>
              {badge.icon}
            </span>
            {!compact && (
              <span className="text-gray-700 dark:text-gray-300 font-medium">
                {badge.name}
              </span>
            )}
            
            {/* Tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
              {badge.name}: {badge.description}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
