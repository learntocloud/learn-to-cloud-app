import Link from "next/link";
import Image from "next/image";
import { SignUpButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import { getAllPhases } from "@/lib/content";

export default async function Home() {
  const { userId } = await auth();
  const phases = getAllPhases();

  return (
    <div>
      {/* Hero with subtle gradient background */}
      <div className="bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-950 pt-12 pb-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center">
          <Image
            src="/logo-cropped.svg"
            alt="Learn to Cloud"
            width={220}
            height={80}
            className="mx-auto mb-4 dark:invert"
            priority
          />
          <p className="text-base text-gray-600 dark:text-gray-400 mb-6 max-w-2xl mx-auto">
            A free, open-source guide to help you land your first cloud engineering role. 
            Learn at your own pace with hands-on projects and real-world skills.
          </p>
          {userId ? (
            <Link
              href="/dashboard"
              className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
            >
              Go to Dashboard →
            </Link>
          ) : (
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <SignUpButton mode="modal">
                <button className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm">
                  Get Started
                </button>
              </SignUpButton>
              <Link
                href="/phases"
                className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                View Curriculum →
              </Link>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">
        {/* Learning Path */}
        <div className="mb-12">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white text-center mb-2">
            Your Learning Path
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-6">
            7 phases designed to take you from complete beginner to cloud-ready
          </p>

          {/* Visual Timeline */}
          <div className="relative">
            {/* Connection line - hidden on mobile */}
            <div className="hidden md:block absolute top-8 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-200 via-blue-400 to-blue-600 dark:from-blue-900 dark:via-blue-700 dark:to-blue-500" />
            
            {/* Phases - horizontal scroll on mobile, grid on desktop */}
            <div className="flex md:grid md:grid-cols-7 gap-4 overflow-x-auto pb-4 md:pb-0 snap-x snap-mandatory">
              {phases.map((phase, index) => (
                <div key={phase.id} className="relative flex-shrink-0 w-40 md:w-auto snap-center">
                  {/* Phase number bubble */}
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

        {/* What Makes LTC Different */}
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
