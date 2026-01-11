import { getPhases } from "@/lib/api";
import Link from "next/link";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

export default async function PhasesPage() {
  const phases = await getPhases();

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Learning Phases</h1>
          <p className="text-gray-600 dark:text-gray-300 mt-2">
            Your roadmap to becoming a Cloud Engineer
          </p>
        </div>

        <div className="space-y-6">
          {phases.map((phase) => (
            <Link key={phase.id} href={`/${phase.slug}`}>
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 hover:shadow-lg hover:border-blue-300 transition-all cursor-pointer">
                <div className="flex items-start gap-6">
                  <div className="flex-shrink-0">
                    <span className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 text-2xl font-bold">
                      {phase.id}
                    </span>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{phase.name}</h2>
                      <span className="text-sm text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                        {phase.estimated_weeks}
                      </span>
                    </div>
                    <p className="text-gray-600 dark:text-gray-300 mb-4">{phase.description}</p>
                    
                    {phase.prerequisites.length > 0 && (
                      <div className="mb-4">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Prerequisites: </span>
                        <span className="text-sm text-gray-500 dark:text-gray-400">
                          {phase.prerequisites.join(" • ")}
                        </span>
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2">
                      {phase.topics.slice(0, 4).map((topic) => (
                        <span
                          key={topic.id}
                          className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-1 rounded"
                        >
                          {topic.name}
                        </span>
                      ))}
                      {phase.topics.length > 4 && (
                        <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-1 rounded">
                          +{phase.topics.length - 4} more
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0 text-gray-400">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
