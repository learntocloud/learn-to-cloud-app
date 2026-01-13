import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { getDashboard, getTodayReflection, getReflectionHistory, getStreak } from "@/lib/api";
import { JournalEntry } from "@/components/journal-entry";
import { JournalHistory } from "@/components/journal-history";
import Link from "next/link";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Journal | Learn to Cloud",
  description: "Reflect on your learning journey",
};

// Contextual prompts based on phase
const PHASE_PROMPTS: Record<number, string[]> = {
  0: [
    "What's your motivation for learning cloud computing?",
    "How do you see cloud skills fitting into your career goals?",
    "What aspects of technology excite you most?",
  ],
  1: [
    "What Linux command surprised you today?",
    "How comfortable are you feeling with the terminal?",
    "What would you build with your new Bash skills?",
  ],
  2: [
    "What programming concept clicked for you today?",
    "How are you finding Python so far?",
    "What's one thing you'd like to automate?",
  ],
  3: [
    "How is the cloud different from what you expected?",
    "What cloud service are you most curious about?",
    "Can you explain a cloud concept to someone else?",
  ],
  4: [
    "What DevOps practice makes the most sense to you?",
    "How do you think about deployment differently now?",
    "What would you containerize first?",
  ],
  5: [
    "What security concept was most eye-opening?",
    "How has this changed how you think about cloud apps?",
    "What security practice will you adopt going forward?",
  ],
};

const GENERAL_PROMPTS = [
  "What did you learn today that you didn't know yesterday?",
  "What concept are you still wrapping your head around?",
  "Did you have any 'aha!' moments?",
  "What would you teach someone about what you learned?",
  "What's blocking your progress right now?",
  "How are you feeling about your learning journey?",
];

function getContextualPrompt(currentPhase: number | null): string {
  const dayOfYear = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 0).getTime()) / (1000 * 60 * 60 * 24));
  
  if (currentPhase !== null && PHASE_PROMPTS[currentPhase]) {
    const phasePrompts = PHASE_PROMPTS[currentPhase];
    return phasePrompts[dayOfYear % phasePrompts.length];
  }
  
  return GENERAL_PROMPTS[dayOfYear % GENERAL_PROMPTS.length];
}

export default async function JournalPage() {
  const { userId } = await auth();
  
  if (!userId) {
    redirect("/sign-in");
  }

  const [dashboard, todayReflection, history, streakData] = await Promise.all([
    getDashboard(),
    getTodayReflection().catch(() => null),
    getReflectionHistory(30).catch(() => []),
    getStreak().catch(() => ({ current_streak: 0, longest_streak: 0 })),
  ]);

  const prompt = getContextualPrompt(dashboard.current_phase);
  const phaseName = dashboard.current_phase !== null 
    ? dashboard.phases.find(p => p.id === dashboard.current_phase)?.name 
    : null;

  // Calculate journal streak (days with reflections in the last 30 days)
  const journalDays = history.length;

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-3xl mx-auto px-4 sm:px-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Learning Journal
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Reflect on your journey through the cloud
            </p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            {journalDays > 0 && (
              <span className="text-gray-500 dark:text-gray-400">
                📝 {journalDays} entries
              </span>
            )}
            {streakData.current_streak > 0 && (
              <span className="text-gray-500 dark:text-gray-400">
                🔥 {streakData.current_streak}d streak
              </span>
            )}
          </div>
        </div>

        {/* Current context */}
        {phaseName && (
          <div className="mb-6 text-sm text-gray-500 dark:text-gray-400">
            Currently on <span className="font-medium text-gray-700 dark:text-gray-300">Phase {dashboard.current_phase}: {phaseName}</span>
          </div>
        )}

        {/* Today's Entry */}
        <div className="mb-10">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Today's Reflection
            </h2>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
            </span>
          </div>
          
          <JournalEntry 
            prompt={prompt}
            existingReflection={todayReflection?.reflection_text}
            currentPhase={dashboard.current_phase}
          />
        </div>

        {/* History */}
        {history.length > 0 && (
          <div>
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-4">
              Past Reflections
            </h2>
            <JournalHistory entries={history} />
          </div>
        )}

        {/* Empty state */}
        {history.length === 0 && !todayReflection && (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <p className="text-lg mb-2">Start your learning journal</p>
            <p className="text-sm">
              Write your first reflection above. Journaling helps solidify what you learn.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
