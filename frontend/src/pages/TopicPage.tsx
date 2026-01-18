import { Link, useParams, Navigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import { useTopicDetail, usePhaseDetail } from '@/lib/hooks';
import type { TopicDetailSchema } from '@/lib/api-client';
import { TopicContent } from '@/components/TopicContent';

// Valid phase slugs
const VALID_PHASE_SLUGS = ["phase0", "phase1", "phase2", "phase3", "phase4", "phase5", "phase6"];

export function TopicPage() {
  const { phaseSlug, topicSlug } = useParams<{ phaseSlug: string; topicSlug: string }>();
  const { isSignedIn, isLoaded } = useUser();

  // Validate slugs
  if (!phaseSlug || !topicSlug || !VALID_PHASE_SLUGS.includes(phaseSlug)) {
    return <Navigate to="/404" replace />;
  }

  // Not signed in - show public view
  if (isLoaded && !isSignedIn) {
    return <TopicPublicView phaseSlug={phaseSlug} topicSlug={topicSlug} />;
  }

  // Signed in - show authenticated view
  if (isLoaded && isSignedIn) {
    return <TopicAuthenticatedView phaseSlug={phaseSlug} topicSlug={topicSlug} />;
  }

  // Loading
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

function TopicPublicView({ phaseSlug, topicSlug }: { phaseSlug: string; topicSlug: string }) {
  const { data: topic, isLoading: topicLoading, error: topicError } = useTopicDetail(phaseSlug, topicSlug);
  const { data: phase, isLoading: phaseLoading } = usePhaseDetail(phaseSlug);

  if (topicLoading || phaseLoading) {
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

  if (topicError || !topic || !phase) {
    return <Navigate to="/404" replace />;
  }

  // Find prev/next topics
  const currentIndex = phase.topics.findIndex(t => t.slug === topicSlug);
  const prevTopic = currentIndex > 0 ? phase.topics[currentIndex - 1] : null;
  const nextTopic = currentIndex < phase.topics.length - 1 ? phase.topics[currentIndex + 1] : null;

  return (
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
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
          topic={topic}
          isAuthenticated={false}
        />

        {/* Sign in prompt */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800 text-center">
          <p className="text-sm text-blue-700 dark:text-blue-300">
            <Link to="/sign-in" className="font-medium hover:underline">
              Sign in
            </Link>{" "}
            to track your progress and answer knowledge questions
          </p>
        </div>

        <TopicNavigation
          phaseSlug={phaseSlug}
          prevTopic={prevTopic}
          nextTopic={nextTopic}
        />
      </div>
    </div>
  );
}

function TopicAuthenticatedView({ phaseSlug, topicSlug }: { phaseSlug: string; topicSlug: string }) {
  const { data: topic, isLoading: topicLoading, error: topicError } = useTopicDetail(phaseSlug, topicSlug);
  const { data: phase, isLoading: phaseLoading } = usePhaseDetail(phaseSlug);

  if (topicLoading || phaseLoading) {
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

  if (topicError || !topic || !phase) {
    return <Navigate to="/404" replace />;
  }

  // If phase is locked
  if (topic.is_locked) {
    const prevPhaseNum = phase.id - 1;
    return (
      <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="mb-6 flex items-center gap-2 text-sm">
            <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              Dashboard
            </Link>
            <span className="text-gray-400">→</span>
            <Link to={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              {phase.name}
            </Link>
          </nav>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="text-6xl mb-4">🔒</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Content Locked</h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You need to complete <strong>Phase {prevPhaseNum}</strong> before you can access content in <strong>{phase.name}</strong>.
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

  // If topic is locked
  if (topic.is_topic_locked) {
    return (
      <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="mb-6 flex items-center gap-2 text-sm">
            <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              Dashboard
            </Link>
            <span className="text-gray-400">→</span>
            <Link to={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              {phase.name}
            </Link>
          </nav>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="text-6xl mb-4">🔒</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Topic Locked</h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You need to complete <strong>{topic.previous_topic_name}</strong> before you can access <strong>{topic.name}</strong>.
            </p>
            <Link
              to={`/${phaseSlug}`}
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Go to {phase.name}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Find prev/next topics
  const currentIndex = phase.topics.findIndex(t => t.slug === topicSlug);
  const prevTopic = currentIndex > 0 ? phase.topics[currentIndex - 1] : null;
  const nextTopic = currentIndex < phase.topics.length - 1 ? phase.topics[currentIndex + 1] : null;

  return (
    <div className="min-h-screen py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
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
      </div>
    </div>
  );
}

function TopicHeader({ topic, isAuthenticated }: {
  topic: TopicDetailSchema;
  isAuthenticated: boolean;
}) {
  // Use API-provided progress values - business logic lives in API, not frontend
  const progress = topic.progress;
  const completedItems = (progress?.steps_completed ?? 0) + (progress?.questions_passed ?? 0);
  const totalItems = (progress?.steps_total ?? 0) + (progress?.questions_total ?? 0);
  const isComplete = progress?.status === 'completed';
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

      {/* What You'll Learn - Learning Objectives */}
      {topic.learning_objectives && topic.learning_objectives.length > 0 && (
        <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-100 dark:border-blue-800/50">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
            <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            What You'll Learn
          </h3>
          <ul className="space-y-1">
            {topic.learning_objectives.map((item) => (
              <li key={item.id} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
                <span className="text-blue-400 mt-1">•</span>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between">
        {topic.estimated_time && (
          <p className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {topic.estimated_time}
          </p>
        )}
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
          <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
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

// Navigation component
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

// Topic page content with progress tracking
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
