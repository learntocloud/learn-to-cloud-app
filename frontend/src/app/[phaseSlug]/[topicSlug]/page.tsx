import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getTopicBySlug, getTopicWithProgressBySlug, getPhaseBySlug } from "@/lib/api";
import { TopicContent } from "@/components/topic-content";
import type { Topic, TopicWithProgress } from "@/lib/types";

// Disable static generation - fetch data at runtime
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
  
  let topic: Topic | TopicWithProgress;
  let isAuthenticated = false;

  // Get phase info for breadcrumb
  const phase = await getPhaseBySlug(phaseSlug);
  if (!phase) {
    notFound();
  }

  if (userId) {
    try {
      topic = await getTopicWithProgressBySlug(phaseSlug, topicSlug);
      isAuthenticated = true;
    } catch {
      topic = await getTopicBySlug(phaseSlug, topicSlug);
    }
  } else {
    topic = await getTopicBySlug(phaseSlug, topicSlug);
  }

  if (!topic) {
    notFound();
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
          <Link href="/phases" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
            Phases
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
            {isAuthenticated && 'items_completed' in topic && (
              <div className="text-right">
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {topic.items_completed}/{topic.items_total}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">completed</div>
              </div>
            )}
          </div>
          
          <p className="text-gray-600 dark:text-gray-300 mb-4">{topic.description}</p>
          
          {topic.estimated_time && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              ⏱️ Estimated time: {topic.estimated_time}
            </p>
          )}

          {isAuthenticated && 'items_completed' in topic && (
            <div className="mt-4">
              <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ 
                    width: `${topic.items_total > 0 ? (topic.items_completed / topic.items_total) * 100 : 0}%` 
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Topic Content (Learning Steps & Checklist) */}
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
              to track your progress and check off items
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
            <Link
              href={`/${phaseSlug}/${nextTopic.slug}`}
              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
            >
              {nextTopic.name} →
            </Link>
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
