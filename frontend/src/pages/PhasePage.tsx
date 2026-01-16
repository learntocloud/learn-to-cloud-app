import { Link, useParams, Navigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import { usePhaseDetail, useUserInfo, useDashboard } from '@/lib/hooks';
import type {
  TopicSummarySchema,
} from '@/lib/api-client';
import { PhaseVerificationForm } from '@/components/PhaseVerificationForm';
import { PhaseCompletionCheck } from '@/components/phase-completion-check';

// Valid phase slugs
const VALID_PHASE_SLUGS = ["phase0", "phase1", "phase2", "phase3", "phase4", "phase5", "phase6"];

// Phase slug to next phase mapping (for celebration modal navigation)
const NEXT_PHASE: Record<string, string | undefined> = {
  phase0: "phase1",
  phase1: "phase2",
  phase2: "phase3",
  phase3: "phase4",
  phase4: "phase5",
  phase5: "phase6",
  phase6: undefined,
};

export function PhasePage() {
  const { phaseSlug } = useParams<{ phaseSlug: string }>();
  const { isSignedIn, isLoaded } = useUser();

  // Validate phase slug
  if (!phaseSlug || !VALID_PHASE_SLUGS.includes(phaseSlug)) {
    return <Navigate to="/404" replace />;
  }

  // If not signed in, show public view
  if (isLoaded && !isSignedIn) {
    return <PhasePublicView phaseSlug={phaseSlug} />;
  }

  // If signed in, show authenticated view
  if (isLoaded && isSignedIn) {
    return <PhaseAuthenticatedView phaseSlug={phaseSlug} />;
  }

  // Loading state
  return (
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    </div>
  );
}

function PhasePublicView({ phaseSlug }: { phaseSlug: string }) {
  const { data: phase, isLoading, error } = usePhaseDetail(phaseSlug);

  if (isLoading) {
    return (
      <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !phase) {
    return <Navigate to="/404" replace />;
  }

  return (
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="mb-6">
          <Link to="/" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm">
            ← Back to Home
          </Link>
        </nav>

        {/* Header */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 mb-8">
          <div className="flex items-center gap-4 mb-6">
            <span className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 text-3xl font-bold">
              {phase.id}
            </span>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{phase.name}</h1>
              <p className="text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-300 mb-6">{phase.description}</p>
        </div>

        {/* Topics (public view) */}
        <section className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
            Topics ({phase.topics.length})
          </h2>
          <div className="space-y-4">
            {phase.topics.map((topic) => (
              <Link
                key={topic.id}
                to={`/${phaseSlug}/${topic.slug}`}
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
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PhaseAuthenticatedView({ phaseSlug }: { phaseSlug: string }) {
  const { data: phase, isLoading, error } = usePhaseDetail(phaseSlug);
  const { data: userInfo } = useUserInfo();
  const { data: dashboard } = useDashboard();

  // Get earned badges from dashboard for celebration modal
  const earnedBadges = dashboard?.badges?.map(b => ({
    id: b.id,
    name: b.name,
    icon: b.icon,
  })) ?? [];

  if (isLoading) {
    return (
      <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !phase) {
    return <Navigate to="/404" replace />;
  }

  const githubUsername = userInfo?.github_username ?? null;

  // Use API-computed value - business logic lives in API, not frontend
  const allTopicsComplete = phase.all_topics_complete;

  // If phase is locked, show locked page
  if (phase.is_locked) {
    const prevPhaseNum = phase.id - 1;
    return (
      <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="mb-6">
            <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm">
              ← Back to Dashboard
            </Link>
          </nav>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="text-6xl mb-4">🔒</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Phase Locked</h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You need to complete <strong>Phase {prevPhaseNum}</strong> before you can access <strong>{phase.name}</strong>.
            </p>
            <Link
              to={`/phase${prevPhaseNum}`}
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Go to Phase {prevPhaseNum}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="mb-6">
          <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm">
            ← Back to Dashboard
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
            {phase.progress && (
              <StatusBadge status={phase.progress.status} />
            )}
          </div>

          <p className="text-gray-600 dark:text-gray-300 mb-6">{phase.description}</p>

          {phase.progress && (
            <ProgressBar
              percentage={phase.progress.percentage}
              status={phase.progress.status}
              size="lg"
            />
          )}

          {phase.objectives && phase.objectives.length > 0 && (
            <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
              <h3 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Objectives</h3>
              <ul className="list-disc list-inside text-sm text-blue-700 dark:text-blue-300">
                {phase.objectives.map((objective, idx) => (
                  <li key={idx}>{objective}</li>
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
            {phase.topics.map((topic, index) => {
              const previousTopic = index > 0 ? phase.topics[index - 1] : null;

              return (
                <TopicCard
                  key={topic.id}
                  topic={topic}
                  phaseSlug={phaseSlug}
                  previousTopicName={previousTopic?.name}
                />
              );
            })}
          </div>
        </section>

        {/* GitHub Submissions / Hands-on Verification */}
        {phase.hands_on_requirements && phase.hands_on_requirements.length > 0 && (
          <section className="mb-8">
            {allTopicsComplete ? (
              <PhaseVerificationForm
                phaseNumber={phase.id}
                requirements={phase.hands_on_requirements}
                submissions={phase.hands_on_submissions || []}
                githubUsername={githubUsername}
                nextPhaseSlug={NEXT_PHASE[phaseSlug]}
                phaseProgress={phase.progress}
                allHandsOnValidated={phase.all_hands_on_validated}
                isPhaseComplete={phase.is_phase_complete}
              />
            ) : (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="text-3xl">🔒</div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                      Hands-on Verification Locked
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Complete all topics above to unlock hands-on verification
                    </p>
                  </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {phase.hands_on_requirements.length} verification{phase.hands_on_requirements.length > 1 ? 's' : ''} to complete:
                  </p>
                  <ul className="space-y-2">
                    {phase.hands_on_requirements.map((req) => (
                      <li key={req.id} className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                        <span className="text-gray-300 dark:text-gray-600">○</span>
                        {req.name}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </section>
        )}

        {/* Phase Completion Celebration Modal */}
        <PhaseCompletionCheck
          phaseNumber={phase.id}
          earnedBadges={earnedBadges}
          nextPhaseSlug={NEXT_PHASE[phaseSlug]}
        />
      </div>
    </div>
  );
}

// Progress components
function StatusBadge({ status }: { status: string }) {
  const statusColors = {
    not_started: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
    in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  };

  const statusLabels = {
    not_started: 'Not Started',
    in_progress: 'In Progress',
    completed: 'Completed',
  };

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[status as keyof typeof statusColors] || statusColors.not_started}`}>
      {statusLabels[status as keyof typeof statusLabels] || 'Not Started'}
    </span>
  );
}

function ProgressBar({ percentage, status, size = 'md' }: { percentage: number; status: string; size?: 'sm' | 'md' | 'lg' }) {
  const heights = { sm: 'h-1', md: 'h-2', lg: 'h-3' };
  const barColors = {
    not_started: 'bg-gray-400',
    in_progress: 'bg-amber-500',
    completed: 'bg-emerald-500',
  };

  return (
    <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full ${heights[size]} overflow-hidden`}>
      <div
        className={`${barColors[status as keyof typeof barColors] || barColors.not_started} ${heights[size]} rounded-full transition-all duration-500`}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

// Topic card component - matches old Next.js styling
function TopicCard({ topic, phaseSlug, previousTopicName }: {
  topic: TopicSummarySchema;
  phaseSlug: string;
  previousTopicName?: string;
}) {
  // Calculate progress
  const stepsCompleted = topic.progress?.steps_completed ?? 0;
  const stepsTotal = topic.steps_count ?? 0;
  const questionsCompleted = topic.progress?.questions_passed ?? 0;
  const questionsTotal = topic.questions_count ?? 0;

  const completedCount = stepsCompleted + questionsCompleted;
  const totalCount = stepsTotal + questionsTotal;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const isComplete = completedCount === totalCount && totalCount > 0;

  // Locked state
  if (topic.is_locked) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden opacity-75">
        <div className="p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-gray-400 dark:text-gray-500">
                  {topic.order}.
                </span>
                <h4 className="font-medium text-gray-500 dark:text-gray-400">{topic.name}</h4>
                {topic.is_capstone && (
                  <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900/50 text-purple-500 dark:text-purple-400 text-xs rounded-full">
                    Capstone
                  </span>
                )}
                <span className="ml-2 text-lg" title="Complete previous topic to unlock">🔒</span>
              </div>
              <p className="text-sm text-gray-400 dark:text-gray-500">{topic.description}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                Complete &quot;{previousTopicName}&quot; to unlock this topic
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Link
      to={`/${phaseSlug}/${topic.slug}`}
      className="block bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-md transition-all"
    >
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                {topic.order}.
              </span>
              <h4 className="font-medium text-gray-900 dark:text-white">{topic.name}</h4>
              {topic.is_capstone && (
                <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 text-xs rounded-full">
                  Capstone
                </span>
              )}
              {isComplete && (
                <span className="ml-2 text-lg" title="Topic completed">✅</span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300">{topic.description}</p>
            {topic.estimated_time && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                ⏱️ {topic.estimated_time}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3 ml-4">
            {/* Progress indicator */}
            {totalCount > 0 && (
              <div className="text-right">
                <div className="text-sm font-medium text-gray-900 dark:text-white">
                  {completedCount}/{totalCount}
                </div>
                <div className="w-20 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${
                      isComplete ? "bg-green-500" : "bg-blue-500"
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            )}
            {/* Arrow to indicate clickable */}
            <svg
              className="w-5 h-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </div>
        </div>
      </div>
    </Link>
  );
}
