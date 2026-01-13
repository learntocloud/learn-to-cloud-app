import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { getDashboard, getStreak } from "@/lib/api";
import { PhaseCard } from "@/components/phase-card";
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
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header Card */}
        <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 mb-4 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {dashboard.user.first_name ? `Welcome back, ${dashboard.user.first_name}` : "Welcome back"} 👋
              </h1>
              <p className="text-gray-500 dark:text-gray-400 mt-1">
                Keep up the great work on your cloud journey!
              </p>
            </div>
            
            {streakData.current_streak > 0 && (
              <div className="flex items-center gap-1.5 text-orange-500 dark:text-orange-400 text-sm font-medium">
                <span>🔥</span> {streakData.current_streak} day streak
              </div>
            )}
          </div>
        </div>

        {/* Progress Card with Stats */}
        <div className="bg-white dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700 p-4 mb-6 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
              <span><span className="font-medium text-gray-700 dark:text-gray-300">{dashboard.phases_completed}/{dashboard.phases_total}</span> Phases</span>
              <span><span className="font-medium text-gray-700 dark:text-gray-300">{dashboard.topics_completed}/{dashboard.topics_total}</span> Topics</span>
              <span><span className="font-medium text-gray-700 dark:text-gray-300">{dashboard.steps_completed}/{dashboard.steps_total}</span> Steps</span>
              <span><span className="font-medium text-gray-700 dark:text-gray-300">{dashboard.questions_completed}/{dashboard.questions_total}</span> Questions</span>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">{Math.round(dashboard.overall_progress)}%</span>
          </div>
          <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
            <div
              className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${dashboard.overall_progress}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-gray-400 dark:text-gray-500">Overall Progress</span>
            <Link
              href="/certificates"
              className="text-xs font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors flex items-center gap-1"
            >
              🏆 View Certificate
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </div>

        {/* Phases Section */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Your Phases
          </h2>
          <div className="grid md:grid-cols-2 gap-5">
            {dashboard.phases.map((phase) => (
              <PhaseCard key={phase.id} phase={phase} showProgress />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
