import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getTopicWithProgressBySlug } from "@/lib/api";
import { getPhaseBySlug, getTopicBySlug } from "@/lib/content";
import { TopicContent } from "@/components/topic-content";
import type { Topic, TopicWithProgress } from "@/lib/types";

// Disable static generation - fetch data at runtime for progress
export const dynamic = "force-dynamic";

interface TopicPageProps {
  params: Promise<{ phaseSlug: string; topicSlug: string }>;
}

// Valid phase slugs
const VALID_PHASE_SLUGS = ["phase0", "phase1", "phase2", "phase3", "phase4", "phase5"];

export default async function TopicPage({ params }: TopicPageProps) {
  const { phaseSlug, topicSlug } = await params;
  
  // Validate phase slug
  if (!VALID_PHASE_SLUGS.includes(phaseSlug)) {
    notFound();
  }

  const { userId } = await auth();
  
  // Get content from local files
  const phase = getPhaseBySlug(phaseSlug);
  if (!phase) {
    notFound();
  }
  
  const topicContent = getTopicBySlug(phaseSlug, topicSlug);
  if (!topicContent) {
    notFound();
  }

  let topic: Topic | TopicWithProgress = topicContent;
  let isAuthenticated = false;
  let isLocked = false;
  let isTopicLocked = false;
  let previousTopicName: string | undefined;

  if (userId) {
    try {
      const topicWithProgress = await getTopicWithProgressBySlug(phaseSlug, topicSlug);
      if (topicWithProgress) {
        topic = topicWithProgress;
        isAuthenticated = true;
        isLocked = topicWithProgress.isLocked;
        isTopicLocked = topicWithProgress.isTopicLocked;
        previousTopicName = topicWithProgress.previousTopicName;
      }
    } catch {
      // Fall back to content without progress
    }
  }

  // If phase is locked, show locked page
  if (isAuthenticated && isLocked) {
    const prevPhaseNum = phase.id - 1;
    return (
      <div className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="mb-6 flex items-center gap-2 text-sm">
            <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              Dashboard
            </Link>
            <span className="text-gray-400">→</span>
            <Link href={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
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
              href={`/phase${prevPhaseNum}`}
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Go to Phase {prevPhaseNum}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // If topic is locked (previous topic not completed), show locked page
  if (isAuthenticated && isTopicLocked) {
    return (
      <div className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="mb-6 flex items-center gap-2 text-sm">
            <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              Dashboard
            </Link>
            <span className="text-gray-400">→</span>
            <Link href={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
              {phase.name}
            </Link>
          </nav>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="text-6xl mb-4">🔒</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Topic Locked</h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You need to complete <strong>{previousTopicName}</strong> before you can access <strong>{topic.name}</strong>.
            </p>
            <Link
              href={`/${phaseSlug}`}
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
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <nav className="mb-6 flex items-center gap-2 text-sm">
          <Link href={isAuthenticated ? "/dashboard" : "/"} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
            {isAuthenticated ? "Dashboard" : "Home"}
          </Link>
          <span className="text-gray-400">→</span>
          <Link href={`/${phaseSlug}`} className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
            {phase.name}
          </Link>
          <span className="text-gray-400">→</span>
          <span className="text-gray-600 dark:text-gray-300">{topic.name}</span>
        </nav>

        {/* Header */}
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
          {'learning_objectives' in topic && topic.learning_objectives && topic.learning_objectives.length > 0 && (
            <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-100 dark:border-blue-800/50">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                What You&apos;ll Learn
              </h3>
              <ul className="space-y-1">
                {topic.learning_objectives.map((item: { id: string; text: string }) => (
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
            {isAuthenticated && 'steps_completed' in topic && (
              (() => {
                const totalItems = topic.steps_total + topic.questions_total;
                const completedItems = topic.steps_completed + topic.questions_passed;
                const isComplete = completedItems === totalItems && totalItems > 0;
                return (
                  <span className={`text-sm font-medium px-2 py-1 rounded ${
                    isComplete
                      ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                      : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400"
                  }`}>
                    {completedItems}/{totalItems} complete
                  </span>
                );
              })()
            )}
          </div>

          {isAuthenticated && 'steps_completed' in topic && (
            (() => {
              const totalItems = topic.steps_total + topic.questions_total;
              const completedItems = topic.steps_completed + topic.questions_passed;
              const isComplete = completedItems === totalItems && totalItems > 0;
              const percentage = totalItems > 0 ? (completedItems / totalItems) * 100 : 0;
              return (
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
              );
            })()
          )}
        </div>

        {/* Topic Content (Learning Steps & Questions) */}
        <TopicContent 
          topic={topic} 
          isAuthenticated={isAuthenticated} 
        />

        {/* Sign in prompt for unauthenticated users */}
        {!isAuthenticated && (
          <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800 text-center">
            <p className="text-sm text-blue-700 dark:text-blue-300">
              <Link href="/sign-in" className="font-medium hover:underline">
                Sign in
              </Link>{" "}
              to track your progress and answer knowledge questions
            </p>
          </div>
        )}

        {/* Navigation */}
        <div className="mt-8 flex justify-between">
          {prevTopic ? (
            <Link
              href={`/${phaseSlug}/${prevTopic.slug}`}
              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
            >
              ← {prevTopic.name}
            </Link>
          ) : (
            <div />
          )}
          {nextTopic ? (
            // Check if next topic should be locked (current topic not completed)
            isAuthenticated && 'questions_passed' in topic && (topic.questions_passed < topic.questions_total || topic.questions_total === 0) ? (
              <span className="text-gray-400 dark:text-gray-500 font-medium cursor-not-allowed flex items-center gap-1">
                🔒 {nextTopic.name}
              </span>
            ) : (
              <Link
                href={`/${phaseSlug}/${nextTopic.slug}`}
                className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
              >
                {nextTopic.name} →
              </Link>
            )
          ) : (
            <Link
              href={`/${phaseSlug}`}
              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
            >
              Back to Phase →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
