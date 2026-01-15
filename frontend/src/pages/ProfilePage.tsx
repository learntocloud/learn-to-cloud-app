import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { usePublicProfile } from '@/lib/hooks';
import { ActivityHeatmap } from '@/components/activity-heatmap';
import { SubmissionsShowcase } from '@/components/submissions-showcase';
import { Badge } from '@/lib/types';

export function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { data: profile, isLoading, error } = usePublicProfile(username || '');

  if (isLoading) {
    return (
      <div className="py-8">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="py-8">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 text-center shadow-sm">
            <div className="text-6xl mb-4">👤</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Profile Not Found</h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              This profile is either private or doesn't exist.
            </p>
            <Link
              to="/"
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Go Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

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
                  <img
                    src={profile.avatar_url}
                    alt={profile.username || 'User'}
                    className="w-14 h-14 rounded-full"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-gray-700 to-gray-900 flex items-center justify-center text-white text-lg font-semibold">
                    {(profile.first_name?.[0] || profile.username?.[0] || '?').toUpperCase()}
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                    {profile.first_name || profile.username || 'Learner'}
                  </h1>
                  <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 text-xs font-medium rounded-full">
                    Phase {profile.current_phase}
                  </span>
                  {profile.streak && profile.streak.current_streak > 0 && (
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

            {/* Share button */}
            <div className="shrink-0">
              <ShareProfileButton profile={profile} username={username || ''} />
            </div>
          </div>
        </div>

        {/* Badge Collection Card - Pokédex style */}
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
        {profile.activity_heatmap && profile.activity_heatmap.days.length > 0 && (
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
        {profile.submissions && profile.submissions.length > 0 && (
          <SubmissionsShowcase submissions={profile.submissions} />
        )}

        {/* Member since */}
        {profile.member_since && (
          <div className="text-center text-sm text-gray-500 dark:text-gray-400 pt-2">
            Member since {new Date(profile.member_since).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
          </div>
        )}
      </div>
    </div>
  );
}

// Pokédex-style Badge Collection
function BadgeCollection({ badges }: { badges: Badge[] }) {
  const ALL_BADGES = [
    { id: 'phase_0_complete', name: 'Cloud Seedling', icon: '🌱', num: '#001', howTo: 'Complete Phase 0: Starting from Zero' },
    { id: 'phase_1_complete', name: 'Terminal Ninja', icon: '🐧', num: '#002', howTo: 'Complete Phase 1: Linux and Bash' },
    { id: 'phase_2_complete', name: 'Code Crafter', icon: '🐍', num: '#003', howTo: 'Complete Phase 2: Programming Fundamentals' },
    { id: 'phase_3_complete', name: 'AI Apprentice', icon: '🤖', num: '#004', howTo: 'Complete Phase 3: AI Tools & Intentional Learning' },
    { id: 'phase_4_complete', name: 'Cloud Explorer', icon: '☁️', num: '#005', howTo: 'Complete Phase 4: Cloud Platform Fundamentals' },
    { id: 'phase_5_complete', name: 'DevOps Rocketeer', icon: '🚀', num: '#006', howTo: 'Complete Phase 5: DevOps Fundamentals' },
    { id: 'phase_6_complete', name: 'Security Guardian', icon: '🔐', num: '#007', howTo: 'Complete Phase 6: Securing Your Cloud Applications' },
    { id: 'streak_7', name: 'Week Warrior', icon: '🔥', num: '#008', howTo: 'Maintain a 7-day learning streak' },
    { id: 'streak_30', name: 'Monthly Master', icon: '💪', num: '#009', howTo: 'Maintain a 30-day learning streak' },
    { id: 'streak_100', name: 'Century Club', icon: '💯', num: '#010', howTo: 'Maintain a 100-day learning streak' },
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
                ? 'bg-gradient-to-b from-amber-100 to-amber-200 dark:from-amber-800/40 dark:to-amber-900/40 border border-amber-300 dark:border-amber-600 shadow-sm'
                : 'bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 opacity-30 grayscale'
            }`}
          >
            <span className="text-lg">{badge.icon}</span>
            <span className={`text-[8px] font-mono mt-0.5 ${isEarned ? 'text-amber-700 dark:text-amber-400' : 'text-gray-400 dark:text-gray-600'}`}>
              {badge.num}
            </span>

            {/* Tooltip - appears below */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 shadow-lg">
              <div className="font-semibold">{badge.name}</div>
              <div className={`text-[10px] mt-0.5 ${isEarned ? 'text-green-400' : 'text-gray-400'}`}>
                {isEarned ? '✓ Earned!' : badge.howTo}
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

// Share Profile Button
interface ShareProfileButtonProps {
  profile: {
    first_name?: string | null;
    phases_completed: number;
    current_phase: number;
    streak?: { current_streak: number } | null;
  };
  username: string;
}

function ShareProfileButton({ profile, username }: ShareProfileButtonProps) {
  const [showShareMenu, setShowShareMenu] = useState(false);
  const [copied, setCopied] = useState(false);

  const profileUrl = `${window.location.origin}/user/${username}`;
  const shareText = `Check out my Learn to Cloud progress! ${profile.phases_completed} phases completed, Phase ${profile.current_phase}, ${profile.streak?.current_streak || 0} day streak 🔥`;

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(profileUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleShareTwitter = () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(profileUrl)}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleShareLinkedIn = () => {
    const url = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(profileUrl)}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowShareMenu(!showShareMenu)}
        className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
        </svg>
        Share
      </button>

      {showShareMenu && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowShareMenu(false)}
          />

          {/* Menu */}
          <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-20 py-1">
            {/* Copy link */}
            <button
              onClick={handleCopyLink}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              {copied ? (
                <>
                  <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Copied!
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                  </svg>
                  Copy Link
                </>
              )}
            </button>

            {/* Twitter */}
            <button
              onClick={handleShareTwitter}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
              </svg>
              Share on X
            </button>

            {/* LinkedIn */}
            <button
              onClick={handleShareLinkedIn}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
              Share on LinkedIn
            </button>
          </div>
        </>
      )}
    </div>
  );
}
