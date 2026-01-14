import { notFound } from "next/navigation";
import { Metadata } from "next";
import { getPublicProfile } from "@/lib/api";
import { ActivityHeatmap } from "@/components/activity-heatmap";
import { SubmissionsShowcase } from "@/components/submissions-showcase";
import { ShareProfileCard } from "@/components/share-profile-card";
import { Badge } from "@/lib/types";
import Image from "next/image";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

interface ProfilePageProps {
  params: Promise<{
    username: string;
  }>;
}

export async function generateMetadata({ params }: ProfilePageProps): Promise<Metadata> {
  const { username } = await params;
  const profile = await getPublicProfile(username);
  
  if (!profile) {
    return { title: "Profile Not Found" };
  }

  const title = `${profile.first_name || username}'s Learn to Cloud Profile`;
  const description = `${profile.phases_completed} phases completed • ${profile.streak.current_streak} day streak`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "profile",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function ProfilePage({ params }: ProfilePageProps) {
  const { username } = await params;
  const profile = await getPublicProfile(username);

  if (!profile) {
    notFound();
  }

  const memberSince = new Date(profile.member_since);
  const memberSinceStr = memberSince.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  return (
    <div className="py-8">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-4">
        {/* Profile Header Card */}
        <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 min-w-0">
              {/* Avatar */}
              <div className="shrink-0">
                {profile.avatar_url ? (
                  <Image
                    src={profile.avatar_url}
                    alt={profile.username || "User"}
                    width={56}
                    height={56}
                    className="rounded-full"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-gray-700 to-gray-900 flex items-center justify-center text-white text-lg font-semibold">
                    {(profile.first_name?.[0] || profile.username?.[0] || "?").toUpperCase()}
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                    {profile.first_name || profile.username || "Learner"}
                  </h1>
                  <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-medium rounded-full">
                    Phase {profile.current_phase}
                  </span>
                  {profile.streak.current_streak > 0 && (
                    <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-300 text-xs font-medium rounded-full">
                      🔥 {profile.streak.current_streak}d
                    </span>
                  )}
                </div>
                {profile.username && (
                  <a
                    href={`https://github.com/${profile.username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors inline-flex items-center gap-1"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                    </svg>
                    @{profile.username}
                  </a>
                )}
              </div>
            </div>

            {/* Share button on right */}
            <div className="shrink-0">
              <ShareProfileCard profile={profile} username={username} />
            </div>
          </div>
        </div>

        {/* Badge Collection Card - Compact Pokédex style */}
        <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Badge Collection
            </h2>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {profile.badges?.length || 0}/10
            </span>
          </div>
          <BadgeCollection badges={profile.badges || []} />
        </div>

        {/* Activity Heatmap Card */}
        {profile.activity_heatmap.days.length > 0 && (
          <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-4">
              Activity
            </h2>
            <ActivityHeatmap
              days={profile.activity_heatmap.days}
              startDate={profile.activity_heatmap.start_date}
              endDate={profile.activity_heatmap.end_date}
            />
          </div>
        )}

        {/* GitHub Submissions Showcase */}
        <SubmissionsShowcase submissions={profile.submissions} />
      </div>
    </div>
  );
}

// Pokédex-style Badge Collection
function BadgeCollection({ badges }: { badges: Badge[] }) {
  const ALL_BADGES = [
    { id: "phase_0_complete", name: "Cloud Seedling", icon: "🌱", num: "#001", howTo: "Complete Phase 0: Starting from Zero" },
    { id: "phase_1_complete", name: "Terminal Ninja", icon: "🐧", num: "#002", howTo: "Complete Phase 1: Linux and Bash" },
    { id: "phase_2_complete", name: "Code Crafter", icon: "🐍", num: "#003", howTo: "Complete Phase 2: Programming Fundamentals" },
    { id: "phase_3_complete", name: "AI Apprentice", icon: "🤖", num: "#004", howTo: "Complete Phase 3: AI Tools & Intentional Learning" },
    { id: "phase_4_complete", name: "Cloud Explorer", icon: "☁️", num: "#005", howTo: "Complete Phase 4: Cloud Platform Fundamentals" },
    { id: "phase_5_complete", name: "DevOps Rocketeer", icon: "🚀", num: "#006", howTo: "Complete Phase 5: DevOps Fundamentals" },
    { id: "phase_6_complete", name: "Security Guardian", icon: "🔐", num: "#007", howTo: "Complete Phase 6: Securing Your Cloud Applications" },
    { id: "streak_7", name: "Week Warrior", icon: "🔥", num: "#008", howTo: "Maintain a 7-day learning streak" },
    { id: "streak_30", name: "Monthly Master", icon: "💪", num: "#009", howTo: "Maintain a 30-day learning streak" },
    { id: "streak_100", name: "Century Club", icon: "💯", num: "#010", howTo: "Maintain a 100-day learning streak" },
  ];

  const earnedIds = new Set(badges.map((b) => b.id));

  return (
    <div className="flex gap-2 overflow-visible flex-wrap">
      {ALL_BADGES.map((badge) => {
        const isEarned = earnedIds.has(badge.id);
        return (
          <div
            key={badge.id}
            className={`group relative shrink-0 w-12 h-14 rounded-lg flex flex-col items-center justify-center transition-all cursor-default ${
              isEarned
                ? "bg-gradient-to-b from-amber-100 to-amber-200 dark:from-amber-800/40 dark:to-amber-900/40 border border-amber-300 dark:border-amber-600 shadow-sm"
                : "bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 opacity-30 grayscale"
            }`}
          >
            <span className="text-lg">{badge.icon}</span>
            <span className={`text-[8px] font-mono mt-0.5 ${isEarned ? "text-amber-700 dark:text-amber-400" : "text-gray-400 dark:text-gray-600"}`}>
              {badge.num}
            </span>
            
            {/* Enhanced Tooltip - appears below */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 shadow-lg">
              <div className="font-semibold">{badge.name}</div>
              <div className={`text-[10px] mt-0.5 ${isEarned ? "text-green-400" : "text-gray-400"}`}>
                {isEarned ? "✓ Earned!" : badge.howTo}
              </div>
              {/* Arrow pointing up */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-gray-900"></div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
