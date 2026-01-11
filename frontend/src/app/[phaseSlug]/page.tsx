import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getPhaseBySlug, getPhaseWithProgressBySlug } from "@/lib/api";
import { TopicCard } from "@/components/topic-card";
import { Checklist } from "@/components/checklist";
import { ProgressBar, StatusBadge } from "@/components/progress";
import type { PhaseDetailWithProgress, Phase, TopicWithProgress, ChecklistItemWithProgress } from "@/lib/types";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

interface PhasePageProps {
  params: Promise<{ phaseSlug: string }>;
}

// Valid phase slugs
const VALID_PHASE_SLUGS = ["phase0", "phase1", "phase2", "phase3", "phase4", "phase5"];

// Phase slug to previous/next mapping
const PHASE_NAV: Record<string, { prev?: string; next?: string }> = {
  phase0: { next: "phase1" },
  phase1: { prev: "phase0", next: "phase2" },
  phase2: { prev: "phase1", next: "phase3" },
  phase3: { prev: "phase2", next: "phase4" },
  phase4: { prev: "phase3", next: "phase5" },
  phase5: { prev: "phase4" },
};

export default async function PhasePage({ params }: PhasePageProps) {
  const { phaseSlug } = await params;
  
  // Validate phase slug
  if (!VALID_PHASE_SLUGS.includes(phaseSlug)) {
    notFound();
  }

  const { userId } = await auth();
  
  let phase: PhaseDetailWithProgress | Phase;
  let topics: TopicWithProgress[] | undefined;
  let checklist: ChecklistItemWithProgress[] | undefined;
  let isAuthenticated = false;

  if (userId) {
    try {
      phase = await getPhaseWithProgressBySlug(phaseSlug);
      topics = (phase as PhaseDetailWithProgress).topics;
      checklist = (phase as PhaseDetailWithProgress).checklist;
      isAuthenticated = true;
    } catch {
      phase = await getPhaseBySlug(phaseSlug);
    }
  } else {
    phase = await getPhaseBySlug(phaseSlug);
  }

  if (!phase) {
    notFound();
  }

  const nav = PHASE_NAV[phaseSlug];

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="mb-6">
          <Link href="/phases" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm">
            ← Back to Phases
          </Link>
        </nav>

        {/* Header */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 mb-8">
          <div className="flex items-start justify-between mb-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 text-3xl font-bold">
                {phase.id}
              </span>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{phase.name}</h1>
                <p className="text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
              </div>
            </div>
            {isAuthenticated && (phase as PhaseDetailWithProgress).progress && (
              <StatusBadge status={(phase as PhaseDetailWithProgress).progress!.status} />
            )}
          </div>
          
          <p className="text-gray-600 dark:text-gray-300 mb-6">{phase.description}</p>

          {isAuthenticated && (phase as PhaseDetailWithProgress).progress && (
            <ProgressBar 
              percentage={(phase as PhaseDetailWithProgress).progress!.percentage} 
              size="lg" 
            />
          )}

          {phase.prerequisites.length > 0 && (
            <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg border border-yellow-200 dark:border-yellow-800">
              <h3 className="font-medium text-yellow-800 dark:text-yellow-200 mb-2">Prerequisites</h3>
              <ul className="list-disc list-inside text-sm text-yellow-700 dark:text-yellow-300">
                {phase.prerequisites.map((prereq, idx) => (
                  <li key={idx}>{prereq}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Topics */}
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
            Topics ({phase.topics.length})
          </h2>
          <div className="space-y-4">
            {isAuthenticated && topics ? (
              topics.map((topic) => (
                <TopicCard key={topic.id} topic={topic} phaseSlug={phaseSlug} />
              ))
            ) : (
              phase.topics.map((topic) => (
                <Link 
                  key={topic.id} 
                  href={`/${phaseSlug}/${topic.slug}`}
                  className="block bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:border-blue-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{topic.order}.</span>
                    <h4 className="font-medium text-gray-900 dark:text-white">{topic.name}</h4>
                    {topic.is_capstone && (
                      <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 text-xs rounded-full">
                        Capstone
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300">{topic.description}</p>
                </Link>
              ))
            )}
          </div>
        </section>

        {/* Checklist */}
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
            Phase Checklist ({phase.checklist.length})
          </h2>
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            {isAuthenticated && checklist ? (
              <Checklist items={checklist} />
            ) : (
              <div className="space-y-2">
                {phase.checklist.map((item) => (
                  <div key={item.id} className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <span className="text-gray-400">☐</span>
                    <span className="text-sm text-gray-700 dark:text-gray-300">{item.text}</span>
                  </div>
                ))}
              </div>
            )}
            {!isAuthenticated && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-4 text-center">
                <Link href="/sign-in" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
                  Sign in
                </Link>{" "}
                to track your progress
              </p>
            )}
          </div>
        </section>

        {/* Navigation */}
        <div className="flex justify-between">
          {nav.prev && (
            <Link
              href={`/${nav.prev}`}
              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
            >
              ← Previous Phase
            </Link>
          )}
          <div /> {/* Spacer */}
          {nav.next && (
            <Link
              href={`/${nav.next}`}
              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
            >
              Next Phase →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
