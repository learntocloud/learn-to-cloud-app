import Link from "next/link";

interface FAQItem {
  question: string;
  answer: string;
}

const faqs: FAQItem[] = [
  {
    question: "What is Learn to Cloud?",
    answer:
      "Learn to Cloud is a structured, self-paced guide to becoming a cloud engineer. It breaks down the journey into phases, each covering essential skills from Linux fundamentals to advanced cloud architecture.",
  },
  {
    question: "How does progress tracking work?",
    answer:
      "Each topic has checklist items you can mark as complete. Your progress is saved automatically and displayed on your dashboard. You can see your overall completion percentage and which phases are in progress or completed.",
  },
  {
    question: "What counts as an activity?",
    answer:
      "Activities include: attempting knowledge questions, completing all questions for a topic, and submitting daily reflections. Your total activity count and activity heatmap are shown on your public profile.",
  },
  {
    question: "How do streaks work?",
    answer:
      "You maintain a streak by completing at least one activity per day. Activities that count toward your streak include answering knowledge questions and submitting daily reflections. Your current streak is displayed on your dashboard.",
  },
  {
    question: "What are knowledge questions?",
    answer:
      "Knowledge questions are AI-graded questions at the end of each topic to test your understanding. You can attempt them multiple times, and your answers are evaluated by an AI that provides feedback on whether you've demonstrated comprehension of the material.",
  },
  {
    question: "What are daily reflections?",
    answer:
      "Daily reflections are optional journal entries where you can write about what you learned, challenges you faced, or goals for tomorrow. They help reinforce learning and contribute to your activity streak.",
  },
  {
    question: "Can I make my profile private?",
    answer:
      "No. Learn to Cloud is built around the principle of public and accountable learning. Keeping profiles public creates positive accountability, motivates consistent progress, and builds a supportive community where learners can inspire each other. This transparency aligns with the open culture of the tech industry.",
  },
  {
    question: "What's shown on my public profile?",
    answer:
      "Your public profile displays: total activities count, activity heatmap (last 365 days), current and longest streaks, phase progress, and GitHub submissions. To have a public profile URL, you need to set a GitHub username in your profile settings.",
  },
  {
    question: "How do GitHub submissions work?",
    answer:
      "Some topics have capstone projects that require you to submit a GitHub repository or URL. These submissions are validated and displayed on your profile to showcase your hands-on work.",
  },
  {
    question: "Can I reset my progress?",
    answer:
      "Currently, there's no bulk reset option. You can uncheck individual checklist items if needed. If you need a full reset, please contact support.",
  },
];

export default function FAQPage() {
  return (
    <div className="min-h-screen py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            Frequently Asked Questions
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300">
            Everything you need to know about using Learn to Cloud
          </p>
        </div>

        {/* FAQ List */}
        <div className="space-y-6">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6"
            >
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                {faq.question}
              </h2>
              <p className="text-gray-600 dark:text-gray-300 leading-relaxed">
                {faq.answer}
              </p>
            </div>
          ))}
        </div>

        {/* Help CTA */}
        <div className="mt-12 text-center">
          <p className="text-gray-600 dark:text-gray-300 mb-4">
            Still have questions?
          </p>
          <a
            href="https://github.com/madebygps/learn-to-cloud-app/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Open an Issue on GitHub
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </a>
        </div>

        {/* Back Link */}
        <div className="mt-8 text-center">
          <Link
            href="/"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
