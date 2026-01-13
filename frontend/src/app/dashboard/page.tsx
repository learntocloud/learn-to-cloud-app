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

  const completedPhases = dashboard.phases.filter(p => p.progress?.status === "completed").length;

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6">
        {/* Compact Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {dashboard.user.first_name ? `Welcome back, ${dashboard.user.first_name}` : "Welcome back"} 👋
            </h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-gray-500 dark:text-gray-400">
              <span>
                <span className="font-medium text-gray-900 dark:text-white">{Math.round(dashboard.overall_progress)}%</span> complete
              </span>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <span>
                <span className="font-medium text-gray-900 dark:text-white">{completedPhases}</span> of {dashboard.phases.length} phases
              </span>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <span>
                <span className="font-medium text-gray-900 dark:text-white">{dashboard.total_completed}</span>/{dashboard.total_items} questions
              </span>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {streakData.current_streak > 0 && (
              <span className="text-sm text-gray-600 dark:text-gray-400">
                🔥 {streakData.current_streak}d
              </span>
            )}
            <Link
              href="/certificates"
              className="text-sm text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
            >
              🏆 Certificates
            </Link>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>Overall Progress</span>
            <span>{Math.round(dashboard.overall_progress)}%</span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
            <div
              className="bg-green-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${dashboard.overall_progress}%` }}
            />
          </div>
        </div>

        {/* Phases */}
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-4">
          Your Phases
        </h2>
        <div className="grid md:grid-cols-2 gap-4">
          {dashboard.phases.map((phase) => (
            <PhaseCard key={phase.id} phase={phase} showProgress />
          ))}
        </div>
      </div>
    </div>
  );
}
