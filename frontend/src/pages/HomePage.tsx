import { Link, useNavigate } from 'react-router-dom';
import { useUser, SignUpButton } from '@clerk/clerk-react';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

/**
 * Abbreviated phase data for homepage timeline display.
 * Full descriptions live in: frontend/public/content/phases/phase{N}/index.json
 * These are intentionally shorter to fit the compact UI.
 */
const PHASES = [
  { id: 0, name: "Starting from Zero", short_description: "Build your IT foundation" },
  { id: 1, name: "Linux and Bash", short_description: "Master the command line" },
  { id: 2, name: "Networking Fundamentals", short_description: "IP, routing, DNS, HTTP" },
  { id: 3, name: "Programming Fundamentals", short_description: "Python, APIs, and databases" },
  { id: 4, name: "Cloud Platform Fundamentals", short_description: "AWS, Azure, or GCP" },
  { id: 5, name: "DevOps Fundamentals", short_description: "Containers, CI/CD, and IaC" },
  { id: 6, name: "Securing Your Cloud Applications", short_description: "Cloud security essentials" },
];

export function HomePage() {
  const { isSignedIn, isLoaded } = useUser();
  const navigate = useNavigate();

  useDocumentTitle('Learn to Cloud - Free Cloud Engineering Guide');

  return (
    <div className="bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="pt-12 pb-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center">
          <img
            src="/logo-cropped.svg"
            alt="Learn to Cloud - Cloud Engineering Learning Platform"
            width={220}
            height={80}
            className="mx-auto mb-4 dark:invert"
          />
          <p className="text-base text-gray-600 dark:text-gray-400 mb-6 max-w-2xl mx-auto">
            A free, open-source guide to help you land your first cloud engineering role.
            Learn at your own pace with hands-on projects and real-world skills.
          </p>
          <HeroCTA isSignedIn={isSignedIn} isLoaded={isLoaded} onDashboard={() => navigate('/dashboard')} />
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">
        <div className="mb-12">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white text-center mb-2">
            Your Learning Path
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-6">
            7 phases designed to take you from complete beginner to cloud-ready
          </p>

          <div className="relative">
            {/* Timeline connector (desktop only) */}
            <div className="hidden md:block absolute top-8 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-200 via-blue-400 to-blue-600 dark:from-blue-900 dark:via-blue-700 dark:to-blue-500" />

            <div className="flex md:grid md:grid-cols-7 gap-4 overflow-x-auto pb-4 md:pb-0 snap-x snap-mandatory">
              {PHASES.map((phase) => (
                <div key={phase.id} className="relative flex-shrink-0 w-40 md:w-auto snap-center">
                  <div className="relative z-10 w-16 h-16 mx-auto mb-3 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 dark:from-blue-600 dark:to-blue-700 flex items-center justify-center shadow-lg">
                    <span className="text-xl font-bold text-white">{phase.id}</span>
                  </div>
                  <div className="text-center">
                    <h3 className="text-xs font-medium text-gray-900 dark:text-white mb-1 line-clamp-2">{phase.name}</h3>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400 line-clamp-2 px-1">{phase.short_description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mb-12">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white text-center mb-6">
            Why Learn to Cloud?
          </h2>
          <div className="grid sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="text-xl mb-2">🎯</div>
              <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-1">Hands-On Focused</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">CTF challenges, real cloud deployments, and practical projects—not just theory</p>
            </div>
            <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="text-xl mb-2">👥</div>
              <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-1">Community Driven</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">Join thousands of learners on Discord for support, study groups, and networking</p>
            </div>
            <div className="p-4 rounded-lg border border-gray-200 dark:border-gray-700">
              <div className="text-xl mb-2">🔓</div>
              <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-1">100% Free & Open Source</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">No paywalls, no upsells. Contribute on GitHub and help improve the curriculum</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function HeroCTA({ isSignedIn, isLoaded, onDashboard }: {
  isSignedIn: boolean | undefined;
  isLoaded: boolean;
  onDashboard: () => void;
}) {
  if (!isLoaded) {
    return (
      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <div className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg opacity-70 animate-pulse">
          Loading...
        </div>
      </div>
    );
  }

  if (isSignedIn) {
    return (
      <button
        onClick={onDashboard}
        aria-label="Go to your dashboard"
        className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        Go to Dashboard →
      </button>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row gap-3 justify-center">
      <SignUpButton mode="modal">
        <button
          aria-label="Create a free account to get started"
          className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Get Started
        </button>
      </SignUpButton>
      <Link
        to="/phases"
        aria-label="Browse the learning curriculum"
        className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        View Curriculum →
      </Link>
    </div>
  );
}
