import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { getDashboard } from "@/lib/api";
import { PhaseCard } from "@/components/phase-card";
import { ProgressBar } from "@/components/progress";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const { userId } = await auth();
  
  if (!userId) {
    redirect("/sign-in");
  }

  const dashboard = await getDashboard();

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Welcome back{dashboard.user.first_name ? `, ${dashboard.user.first_name}` : ""}! 👋
          </h1>
          <p className="text-gray-600 dark:text-gray-300 mt-2">Track your progress through Learn to Cloud</p>
        </div>

        {/* Overall Progress Card */}
        <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-8 mb-8 text-white">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div>
              <h2 className="text-2xl font-bold mb-2">Overall Progress</h2>
              <p className="text-blue-100">
                {dashboard.total_completed} of {dashboard.total_items} items completed
              </p>
              {dashboard.current_phase !== null && (
                <p className="text-blue-100 mt-1">
                  Currently on Phase {dashboard.current_phase}
                </p>
              )}
            </div>
            <div className="flex items-center gap-4">
              <div className="text-5xl font-bold">
                {Math.round(dashboard.overall_progress)}%
              </div>
              <div className="w-32">
                <div className="w-full bg-blue-400/30 rounded-full h-4 overflow-hidden">
                  <div
                    className="bg-white h-4 rounded-full transition-all duration-500"
                    style={{ width: `${dashboard.overall_progress}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="text-3xl font-bold text-blue-600">{dashboard.phases.length}</div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Total Phases</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="text-3xl font-bold text-green-600">
              {dashboard.phases.filter(p => p.progress?.status === "completed").length}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Phases Completed</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="text-3xl font-bold text-yellow-600">
              {dashboard.phases.filter(p => p.progress?.status === "in_progress").length}
            </div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">In Progress</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="text-3xl font-bold text-gray-600 dark:text-gray-300">{dashboard.total_items}</div>
            <div className="text-gray-600 dark:text-gray-300 text-sm">Total Items</div>
          </div>
        </div>

        {/* Phases Grid */}
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Your Phases</h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {dashboard.phases.map((phase) => (
            <PhaseCard key={phase.id} phase={phase} showProgress />
          ))}
        </div>
      </div>
    </div>
  );
}
