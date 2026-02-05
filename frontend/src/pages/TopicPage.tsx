import { useMemo } from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import { useTopicDetail, usePhaseDetail } from '@/lib/hooks';
import type { TopicDetailSchema } from '@/lib/api-client';
import { TopicContent } from '@/components/TopicContent';
import { PROGRESS_STATUS, isValidPhaseSlug } from '@/lib/constants';

// Infer phase type from hook return
type PhaseData = NonNullable<ReturnType<typeof usePhaseDetail>['data']>;

function TopicLoadingState() {
  return (
    <TopicPageLayout>
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-label="Loading" />
      </div>
    </TopicPageLayout>
  );
}

function TopicPageLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen py-8 bg-linear-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {children}
      </div>
    </div>
  );
}

function useTopicNavigation(phase: PhaseData | null | undefined, topicSlug: string) {
  return useMemo(() => {
    if (!phase) return { prevTopic: null, nextTopic: null };
    const currentIndex = phase.topics.findIndex((t) => t.slug === topicSlug);
    return {
      prevTopic: currentIndex > 0 ? phase.topics[currentIndex - 1] : null,
      nextTopic: currentIndex < phase.topics.length - 1 ? phase.topics[currentIndex + 1] : null,
    };
  }, [phase, topicSlug]);
}

export function TopicPage() {
  const { phaseSlug, topicSlug } = useParams<{ phaseSlug: string; topicSlug: string }>();
  const { isSignedIn, isLoaded } = useUser();

  if (!phaseSlug || !topicSlug || !isValidPhaseSlug(phaseSlug)) {
    return <Navigate to="/404" replace />;
  }

  if (isLoaded && !isSignedIn) {
    return <TopicPublicView phaseSlug={phaseSlug} topicSlug={topicSlug} />;
  }

  if (isLoaded && isSignedIn) {
    return <TopicAuthenticatedView phaseSlug={phaseSlug} topicSlug={topicSlug} />;
  }

  return <TopicLoadingState />;
}

function TopicPublicView({ phaseSlug, topicSlug }: { phaseSlug: string; topicSlug: string }) {
  const { data: topic, isLoading: topicLoading, error: topicError } = useTopicDetail(phaseSlug, topicSlug);
  const { data: phase, isLoading: phaseLoading } = usePhaseDetail(phaseSlug);
  const { prevTopic, nextTopic } = useTopicNavigation(phase, topicSlug);

  if (topicLoading || phaseLoading) {
    return <TopicLoadingState />;
  }

  if (topicError || !topic || !phase) {
    return <Navigate to="/404" replace />;
  }

  return (
    <TopicPageLayout>
      {/* Public view links to Home; authenticated view links to Dashboard */}
      <nav className="mb-6 flex items-center gap-2 text-sm">
        <Link to="/" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
          Home
        </Link>
          <span className="text-gray-400">→</span>
          <Link to={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
            {phase.name}
          </Link>
          <span className="text-gray-400">→</span>
          <span className="text-gray-600 dark:text-gray-300">{topic.name}</span>
        </nav>

        <TopicHeader topic={topic} isAuthenticated={false} />

        <TopicContent
          key={topic.id}
          topic={topic}
          isAuthenticated={false}
        />

        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800 text-center">
          <p className="text-sm text-blue-700 dark:text-blue-300">
            <Link to="/sign-in" className="font-medium hover:underline">
              Sign in
            </Link>{" "}
            to track your progress and save completed steps
          </p>
        </div>

        <TopicNavigation
          phaseSlug={phaseSlug}
          prevTopic={prevTopic}
          nextTopic={nextTopic}
        />
    </TopicPageLayout>
  );
}

function TopicAuthenticatedView({ phaseSlug, topicSlug }: { phaseSlug: string; topicSlug: string }) {
  const { data: topic, isLoading: topicLoading, error: topicError } = useTopicDetail(phaseSlug, topicSlug);
  const { data: phase, isLoading: phaseLoading } = usePhaseDetail(phaseSlug);
  const { prevTopic, nextTopic } = useTopicNavigation(phase, topicSlug);

  if (topicLoading || phaseLoading) {
    return <TopicLoadingState />;
  }

  if (topicError || !topic || !phase) {
    return <Navigate to="/404" replace />;
  }

  return (
    <TopicPageLayout>
      <nav className="mb-6 flex items-center gap-2 text-sm">
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
          Dashboard
        </Link>
        <span className="text-gray-400">→</span>
        <Link to={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
          {phase.name}
        </Link>
        <span className="text-gray-400">→</span>
        <span className="text-gray-600 dark:text-gray-300">{topic.name}</span>
      </nav>

      <TopicPageContent
        topic={topic}
        phaseSlug={phaseSlug}
        prevTopic={prevTopic}
        nextTopic={nextTopic}
      />
    </TopicPageLayout>
  );
}

function TopicHeader({ topic, isAuthenticated }: {
  topic: TopicDetailSchema;
  isAuthenticated: boolean;
}) {
  // Use API-provided progress values - business logic lives in API, not frontend
  const progress = topic.progress;
  const completedItems = progress?.steps_completed ?? 0;
  const totalItems = progress?.steps_total ?? 0;
  const isComplete = progress?.status === PROGRESS_STATUS.COMPLETED;
  const percentage = progress?.percentage ?? 0;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 mb-8">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
              Topic {topic.order}
            </span>
            {topic.is_capstone && (
              <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 text-xs rounded-full">
                Capstone
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{topic.name}</h1>
        </div>
      </div>

      <p className="text-gray-600 dark:text-gray-300 mb-4">{topic.description}</p>

      <div className="flex items-center justify-end">
        {isAuthenticated && totalItems > 0 && (
          <span className={`text-sm font-medium px-2 py-1 rounded ${
            isComplete
              ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
              : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
          }`}>
            {completedItems}/{totalItems} complete
          </span>
        )}
      </div>

      {isAuthenticated && totalItems > 0 && (
        <div className="mt-4">
          <div
            className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden"
            role="progressbar"
            aria-valuenow={percentage}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Topic progress: ${completedItems} of ${totalItems} complete`}
          >
            <div
              className={`h-full transition-all duration-300 ${
                isComplete ? "bg-green-500" : "bg-blue-500"
              }`}
              style={{ width: `${percentage}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function TopicNavigation({ phaseSlug, prevTopic, nextTopic }: {
  phaseSlug: string;
  prevTopic: { slug: string; name: string } | null;
  nextTopic: { slug: string; name: string } | null;
}) {
  return (
    <div className="mt-8 flex justify-between">
      {prevTopic ? (
        <Link
          to={`/${phaseSlug}/${prevTopic.slug}`}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          ← {prevTopic.name}
        </Link>
      ) : (
        <div />
      )}
      {nextTopic ? (
        <Link
          to={`/${phaseSlug}/${nextTopic.slug}`}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          {nextTopic.name} →
        </Link>
      ) : (
        <Link
          to={`/${phaseSlug}`}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          Complete Phase: Hands-on Verification →
        </Link>
      )}
    </div>
  );
}

function TopicPageContent({
  topic,
  phaseSlug,
  prevTopic,
  nextTopic,
}: {
  topic: TopicDetailSchema;
  phaseSlug: string;
  prevTopic: { slug: string; name: string } | null;
  nextTopic: { slug: string; name: string } | null;
}) {
  return (
    <>
      <TopicHeader
        topic={topic}
        isAuthenticated={true}
      />

      <TopicContent
        key={topic.id}
        topic={topic}
        isAuthenticated={true}
      />

      <TopicNavigation
        phaseSlug={phaseSlug}
        prevTopic={prevTopic}
        nextTopic={nextTopic}
      />
    </>
  );
}
