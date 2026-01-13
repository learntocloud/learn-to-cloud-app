import { notFound } from "next/navigation";
import { Metadata } from "next";
import { getPublicProfile } from "@/lib/api";
import { ActivityHeatmap } from "@/components/activity-heatmap";
import { SubmissionsShowcase } from "@/components/submissions-showcase";
import { ShareProfileCard } from "@/components/share-profile-card";
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
  const description = `${profile.completed_topics} items completed • Phase ${profile.current_phase} • ${profile.streak.current_streak} day streak`;

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
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Profile Header */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <div className="shrink-0">
              {profile.avatar_url ? (
                <Image
                  src={profile.avatar_url}
                  alt={profile.username || "User"}
                  width={96}
                  height={96}
                  className="rounded-full"
                />
              ) : (
                <div className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-3xl font-bold">
                  {(profile.first_name?.[0] || profile.username?.[0] || "?").toUpperCase()}
                </div>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
                {profile.first_name || profile.username || "Learner"}
              </h1>
              {profile.username && (
                <a
                  href={`https://github.com/${profile.username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                  </svg>
                  @{profile.username}
                </a>
              )}
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                Member since {memberSinceStr}
              </p>
            </div>

            {/* Streak Badge & Share Button */}
            <div className="shrink-0 flex flex-col items-end gap-3">
              {profile.streak.current_streak > 0 && (
                <div className="flex items-center gap-2 px-4 py-2 bg-orange-100 dark:bg-orange-900/30 rounded-full">
                  <span className="text-2xl">🔥</span>
                  <div className="text-right">
                    <div className="text-lg font-bold text-orange-600 dark:text-orange-400">
                      {profile.streak.current_streak}
                    </div>
                    <div className="text-xs text-orange-600/70 dark:text-orange-400/70">
                      day streak
                    </div>
                  </div>
                </div>
              )}
              <ShareProfileCard profile={profile} username={username} />
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">
              {profile.current_phase}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Current Phase</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
            <div className="text-2xl font-bold text-green-600">
              {profile.completed_topics}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Items Completed</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
            <div className="text-2xl font-bold text-purple-600">
              {profile.streak.longest_streak}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Longest Streak</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">
              {profile.activity_heatmap.total_activities}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Total Activities</div>
          </div>
        </div>

        {/* Activity Heatmap */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-6">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
            Activity
          </h2>
          {profile.activity_heatmap.days.length > 0 ? (
            <ActivityHeatmap
              days={profile.activity_heatmap.days}
              startDate={profile.activity_heatmap.start_date}
              endDate={profile.activity_heatmap.end_date}
            />
          ) : (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">
              No activity yet. Start learning to see your progress!
            </p>
          )}
        </div>

        {/* GitHub Submissions Showcase */}
        <SubmissionsShowcase submissions={profile.submissions} />
      </div>
    </div>
  );
}
