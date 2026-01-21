import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const FAQ_ITEMS = [
  {
    id: 'what-is-ltc',
    question: "What is Learn to Cloud?",
    answer: "Learn to Cloud is a free, open-source guide designed to help people learn cloud computing from zero to job-ready. It provides a structured curriculum with hands-on projects and community support."
  },
  {
    id: 'is-it-free',
    question: "Is Learn to Cloud really free?",
    answer: "Yes! Learn to Cloud is completely free. The curriculum, projects, and community support are all available at no cost. You may need cloud accounts for some hands-on projects, but most cloud providers offer free tiers."
  },
  {
    id: 'prior-experience',
    question: "Do I need prior programming experience?",
    answer: "No prior experience is required. Phase 0 covers the basics, and you'll learn programming concepts as you progress through the curriculum."
  },
  {
    id: 'which-cloud',
    question: "Which cloud provider should I learn?",
    answer: "We support learning AWS, Azure, and GCP. The fundamentals are similar across providers. Pick one to start (Azure is recommended for beginners due to its free tier), and you can learn others later."
  },
  {
    id: 'how-long',
    question: "How long does it take to complete?",
    answer: "This depends on your pace and prior experience. Most learners complete the curriculum in 3-6 months while studying part-time. Each phase has estimated timeframes."
  },
  {
    id: 'get-help',
    question: "How do I get help if I'm stuck?",
    answer: "Join our Discord community! There are thousands of learners and mentors ready to help. You can also open GitHub issues for curriculum-related questions."
  },
  {
    id: 'certificate',
    question: "Do I get a certificate?",
    answer: "Yes! When you complete all phases and hands-on verifications, you'll earn a verifiable certificate that you can share with employers."
  },
  {
    id: 'contribute',
    question: "Can I contribute to Learn to Cloud?",
    answer: "Absolutely! Learn to Cloud is open source. You can contribute by improving the curriculum, fixing bugs, translating content, or helping other learners in the community."
  }
];

export function FAQPage() {
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    document.title = 'FAQ - Learn to Cloud';
  }, []);

  const toggleItem = (id: string) => {
    setOpenId(openId === id ? null : id);
  };

  return (
    <main className="min-h-screen py-12 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Frequently Asked Questions
          </h1>
          <p className="mt-3 text-gray-600 dark:text-gray-300">
            Everything you need to know about Learn to Cloud
          </p>
        </div>

        <div className="space-y-3">
          {FAQ_ITEMS.map((item) => {
            const isOpen = openId === item.id;
            return (
              <article
                key={item.id}
                className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
              >
                <button
                  onClick={() => toggleItem(item.id)}
                  aria-expanded={isOpen}
                  aria-controls={`faq-answer-${item.id}`}
                  className="w-full px-6 py-4 text-left flex items-center justify-between gap-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500"
                >
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {item.question}
                  </h2>
                  <span
                    className={`flex-shrink-0 text-gray-500 dark:text-gray-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                    aria-hidden="true"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </span>
                </button>
                <div
                  id={`faq-answer-${item.id}`}
                  role="region"
                  aria-labelledby={item.id}
                  className={`overflow-hidden transition-all duration-200 ${isOpen ? 'max-h-96' : 'max-h-0'}`}
                >
                  <p className="px-6 pb-4 text-gray-600 dark:text-gray-300">
                    {item.answer}
                  </p>
                </div>
              </article>
            );
          })}
        </div>

        <section className="mt-12 text-center">
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Still have questions?
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="https://discord.gg/learntocloud"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Join Discord (opens in new tab)"
              className="inline-flex items-center justify-center px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
              Join Discord
            </a>
            <Link
              to="/phases"
              className="inline-flex items-center justify-center px-6 py-3 border-2 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 font-medium rounded-lg hover:border-gray-300 dark:hover:border-gray-600 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
              View Curriculum
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
