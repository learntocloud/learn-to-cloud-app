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
      <div className="bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-950 pt-8 pb-6">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 text-center">
          <Image
            src="/logo-cropped.svg"
            alt="Learn to Cloud"
            width={220}
            height={80}
            className="mx-auto mb-2 dark:invert"
            priority
          />
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Anyone can learn cloud engineering with the right guide and discipline
          </p>
          {!userId && (
            <SignUpButton mode="modal">
              <button className="px-5 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm">
                Get Started
              </button>
            </SignUpButton>
          )}
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
        {/* Features */}
        <div className="flex justify-center flex-wrap gap-3 mb-6">
          <span className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-full text-xs font-medium text-gray-700 dark:text-gray-300">
            📊 Progress tracking
          </span>
          <span className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-full text-xs font-medium text-gray-700 dark:text-gray-300">
            🧠 Quizzes
          </span>
          <span className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-full text-xs font-medium text-gray-700 dark:text-gray-300">
            🏆 Certificates
          </span>
          <span className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-full text-xs font-medium text-gray-700 dark:text-gray-300">
            💻 Capstone projects
          </span>
        </div>

        {/* Phases header */}
        <h2 className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-3">
          6 Phases
        </h2>

        {/* Phases - 3 column grid */}
        <div className="grid md:grid-cols-3 gap-4 mb-4">
          {phases.map((phase) => (
            <div key={phase.id} className="p-4 rounded-lg border border-gray-200 dark:border-gray-700 h-full">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg font-semibold text-blue-500 dark:text-blue-400">{phase.id}</span>
                <h3 className="text-sm font-medium text-gray-900 dark:text-white">{phase.name}</h3>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{phase.short_description}</p>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="text-center py-4 space-y-4">
          {userId ? (
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
            >
              Go to Dashboard →
            </Link>
          ) : (
            <>
              <Link
                href="/phases"
                className="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium border border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
              >
                View Curriculum →
              </Link>
              <div className="flex justify-center flex-wrap gap-2">
                <span className="px-3 py-1 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium">
                  ✓ Free forever
                </span>
                <span className="px-3 py-1 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium">
                  ✓ Open source
                </span>
                <span className="px-3 py-1 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium">
                  ✓ No credit card
                </span>
                <span className="px-3 py-1 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-xs font-medium">
                  ✓ Updated monthly
                </span>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <footer className="pt-8 mt-8 border-t border-gray-200 dark:border-gray-800 text-center">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            © 2026 Learn to Cloud by{" "}
            <a
              href="https://x.com/madebygps"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              Gwyneth Peña-Siguenza
            </a>
            {" & "}
            <a
              href="https://x.com/rishabincloud"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              Rishab Kumar
            </a>
            {" · "}
            <a
              href="https://creativecommons.org/licenses/by/4.0/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              CC BY 4.0
            </a>
          </p>
        </footer>
      </div>
    </div>
  );
}
