import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { getDashboard, getStreak } from "@/lib/api";
import { PhaseRoadmap } from "@/components/phase-roadmap";
import Link from "next/link";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const { userId } = await auth();
  
  if (!userId) {
    redirect("/sign-in");
  }

  const [dashboard, streakData] = await Promise.all([
    getDashboard(),
    getStreak().catch(() => ({ current_streak: 0, longest_streak: 0, last_activity_date: null })),
  ]);

  return (
    <div className="py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Combined Header + Progress */}
        <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 mb-6 shadow-sm">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                {dashboard.user.first_name ? `Welcome back, ${dashboard.user.first_name}` : "Welcome back"} 👋
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                Keep up the great work on your cloud journey!
              </p>
            </div>
            
            {streakData.current_streak > 0 && (
              <span className="text-orange-500 dark:text-orange-400 text-sm font-medium shrink-0">
                🔥 {streakData.current_streak} day streak
              </span>
            )}
          </div>
          
          {/* Progress bar */}
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
              <div
                className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${dashboard.overall_progress}%` }}
              />
            </div>
            <div className="text-right shrink-0">
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 tabular-nums">
                {dashboard.phases_completed}/{dashboard.phases_total} phases
              </span>
              <Link
                href="/certificates"
                className="block text-xs font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors mt-0.5"
              >
                🏆 View Certificate
              </Link>
            </div>
          </div>
        </div>

        {/* Phases Section */}
        <div className="mb-6">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">
            Your Journey
          </h2>
          <PhaseRoadmap phases={dashboard.phases} />
        </div>
      </div>
    </div>
  );
}
