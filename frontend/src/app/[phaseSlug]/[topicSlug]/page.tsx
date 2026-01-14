import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getTopicWithProgressBySlug } from "@/lib/api";
import { getPhaseBySlug, getTopicBySlug } from "@/lib/content";
import { TopicPageContent } from "@/components/topic-page-content";
import type { Topic, TopicWithProgress } from "@/lib/types";

// Disable static generation - fetch data at runtime for progress
export const dynamic = "force-dynamic";

interface TopicPageProps {
  params: Promise<{ phaseSlug: string; topicSlug: string }>;
}

// Valid phase slugs
const VALID_PHASE_SLUGS = ["phase0", "phase1", "phase2", "phase3", "phase4", "phase5", "phase6"];

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

        {/* Client component for dynamic progress updates */}
        <TopicPageContent
          topic={topic}
          phase={{ id: phase.id, name: phase.name, slug: phase.slug }}
          isAuthenticated={isAuthenticated}
          prevTopic={prevTopic ? { slug: prevTopic.slug, name: prevTopic.name } : null}
          nextTopic={nextTopic ? { slug: nextTopic.slug, name: nextTopic.name } : null}
        />
      </div>
    </div>
  );
}
