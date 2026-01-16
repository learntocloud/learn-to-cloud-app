import { Link } from 'react-router-dom';

const FAQ_ITEMS = [
  {
    question: "What is Learn to Cloud?",
    answer: "Learn to Cloud is a free, open-source guide designed to help people learn cloud computing from zero to job-ready. It provides a structured curriculum with hands-on projects and community support."
  },
  {
    question: "Is Learn to Cloud really free?",
    answer: "Yes! Learn to Cloud is completely free. The curriculum, projects, and community support are all available at no cost. You may need cloud accounts for some hands-on projects, but most cloud providers offer free tiers."
  },
  {
    question: "Do I need prior programming experience?",
    answer: "No prior experience is required. Phase 0 covers the basics, and you'll learn programming concepts as you progress through the curriculum."
  },
  {
    question: "Which cloud provider should I learn?",
    answer: "We support learning AWS, Azure, and GCP. The fundamentals are similar across providers. Pick one to start (Azure is recommended for beginners due to its free tier), and you can learn others later."
  },
  {
    question: "How long does it take to complete?",
    answer: "This depends on your pace and prior experience. Most learners complete the curriculum in 3-6 months while studying part-time. Each phase has estimated timeframes."
  },
  {
    question: "How do I get help if I'm stuck?",
    answer: "Join our Discord community! There are thousands of learners and mentors ready to help. You can also open GitHub issues for curriculum-related questions."
  },
  {
    question: "Do I get a certificate?",
    answer: "Yes! When you complete all phases and hands-on verifications, you'll earn a verifiable certificate that you can share with employers."
  },
  {
    question: "Can I contribute to Learn to Cloud?",
    answer: "Absolutely! Learn to Cloud is open source. You can contribute by improving the curriculum, fixing bugs, translating content, or helping other learners in the community."
  }
];

export function FAQPage() {
  return (
    <div className="min-h-screen py-12 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Frequently Asked Questions
          </h1>
          <p className="mt-3 text-gray-600 dark:text-gray-300">
            Everything you need to know about Learn to Cloud
          </p>
        </div>

        <div className="space-y-6">
          {FAQ_ITEMS.map((item, index) => (
            <div
              key={index}
              className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6"
            >
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                {item.question}
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                {item.answer}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-12 text-center">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Still have questions?
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="https://discord.gg/learntocloud"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Join Discord
            </a>
            <Link
              to="/phases"
              className="inline-flex items-center justify-center px-6 py-3 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 font-medium rounded-lg hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
            >
              View Curriculum
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
