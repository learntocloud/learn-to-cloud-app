import { notFound } from "next/navigation";
import { Metadata } from "next";
import { getPublicProfile } from "@/lib/api";
import { ActivityHeatmap } from "@/components/activity-heatmap";
import { BadgesDisplay } from "@/components/badges-display";
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
      <div className="max-w-3xl mx-auto px-4 sm:px-6">
        {/* Profile Header - Clean & Minimal */}
        <div className="flex items-center gap-4 mb-6">
          {/* Avatar */}
          <div className="shrink-0">
            {profile.avatar_url ? (
              <Image
                src={profile.avatar_url}
                alt={profile.username || "User"}
                width={64}
                height={64}
                className="rounded-full"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-gray-700 to-gray-900 flex items-center justify-center text-white text-xl font-semibold">
                {(profile.first_name?.[0] || profile.username?.[0] || "?").toUpperCase()}
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
              {profile.first_name || profile.username || "Learner"}
            </h1>
            <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
              {profile.username && (
                <a
                  href={`https://github.com/${profile.username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
                >
                  @{profile.username}
                </a>
              )}
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <span>{memberSinceStr}</span>
            </div>
          </div>

          {/* Actions */}
          <div className="shrink-0 flex items-center gap-2">
            {profile.streak.current_streak > 0 && (
              <span className="text-sm text-gray-600 dark:text-gray-400">
                🔥 {profile.streak.current_streak}d
              </span>
            )}
            <ShareProfileCard profile={profile} username={username} />
          </div>
        </div>

        {/* Stats Row with Badges */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mb-8 text-sm">
          <div>
            <span className="font-semibold text-gray-900 dark:text-white">{profile.current_phase}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1">phase</span>
          </div>
          <div>
            <span className="font-semibold text-gray-900 dark:text-white">{profile.completed_topics}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1">completed</span>
          </div>
          <div>
            <span className="font-semibold text-gray-900 dark:text-white">{profile.streak.longest_streak}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1">best streak</span>
          </div>
          <div>
            <span className="font-semibold text-gray-900 dark:text-white">{profile.activity_heatmap.total_activities}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1">activities</span>
          </div>
          
          {/* Badges inline */}
          {profile.badges?.length > 0 && (
            <div className="w-full sm:w-auto sm:ml-auto">
              <BadgesDisplay badges={profile.badges} compact />
            </div>
          )}
        </div>

        {/* Activity Heatmap - Centered */}
        {profile.activity_heatmap.days.length > 0 && (
          <div className="mb-8 flex justify-center">
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
