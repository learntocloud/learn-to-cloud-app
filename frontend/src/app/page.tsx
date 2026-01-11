import Link from "next/link";
import { SignInButton, SignUpButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import { getPhases } from "@/lib/api";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

export default async function Home() {
  const { userId } = await auth();
  const phases = await getPhases();

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-blue-600 to-blue-800 text-white py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="text-4xl md:text-6xl font-bold mb-6">
            Learn to Cloud ☁️
          </h1>
          <p className="text-xl md:text-2xl text-blue-100 mb-8 max-w-2xl mx-auto">
            The most up-to-date guide to becoming a cloud engineer.
          </p>
          <div className="flex gap-4 justify-center">
            {userId ? (
              <Link
                href="/dashboard"
                className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors"
              >
                Go to Dashboard →
              </Link>
            ) : (
              <>
                <SignUpButton mode="modal">
                  <button className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors">
                    Get Started Free
                  </button>
                </SignUpButton>
                <SignInButton mode="modal">
                  <button className="bg-transparent border-2 border-white text-white px-8 py-3 rounded-lg font-semibold hover:bg-white/10 transition-colors">
                    Sign In
                  </button>
                </SignInButton>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-16 bg-white dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-12">
            Why Learn to Cloud?
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center p-6">
              <div className="text-4xl mb-4">🎯</div>
              <h3 className="text-xl font-semibold mb-2 text-gray-900 dark:text-white">Structured Path</h3>
              <p className="text-gray-600 dark:text-gray-300">
                Follow a clear, step-by-step guide from fundamentals to advanced cloud engineering.
              </p>
            </div>
            <div className="text-center p-6">
              <div className="text-4xl mb-4">📊</div>
              <h3 className="text-xl font-semibold mb-2 text-gray-900 dark:text-white">Track Progress</h3>
              <p className="text-gray-600 dark:text-gray-300">
                Mark topics complete, check off milestones, and see your overall progress.
              </p>
            </div>
            <div className="text-center p-6">
              <div className="text-4xl mb-4">💪</div>
              <h3 className="text-xl font-semibold mb-2 text-gray-900 dark:text-white">Hands-On Projects</h3>
              <p className="text-gray-600 dark:text-gray-300">
                Build real-world skills with capstone projects at the end of each phase.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Phases Overview */}
      <section className="py-16 bg-gray-50 dark:bg-gray-950">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-4">
            The Learning Path
          </h2>
          <p className="text-gray-600 dark:text-gray-300 text-center mb-12 max-w-2xl mx-auto">
            6 phases designed to take you from zero knowledge to cloud engineer
          </p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {phases.map((phase) => (
              <Link key={phase.id} href={`/${phase.slug}`}>
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 hover:shadow-lg hover:border-blue-300 transition-all cursor-pointer h-full">
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-3xl font-bold text-blue-600">{phase.id}</span>
                    <div>
                      <h3 className="font-semibold text-lg text-gray-900 dark:text-white">{phase.name}</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{phase.estimated_weeks}</p>
                    </div>
                  </div>
                  <p className="text-gray-600 dark:text-gray-300 text-sm line-clamp-2">{phase.description}</p>
                  <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 mt-4">
                    <span>📚 {phase.topics.length} topics</span>
                    <span>✅ {phase.checklist.length} milestones</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 bg-blue-600 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl font-bold mb-4">Ready to Start Your Cloud Journey?</h2>
          <p className="text-blue-100 mb-8">Join thousands of learners on the path to cloud engineering.</p>
          {userId ? (
            <Link
              href="/dashboard"
              className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors inline-block"
            >
              Go to Dashboard →
            </Link>
          ) : (
            <SignUpButton mode="modal">
              <button className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors">
                Create Free Account
              </button>
            </SignUpButton>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 bg-gray-900 dark:bg-black text-gray-400">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <p>
            © 2026 Learn to Cloud by{" "}
            <a
              href="https://x.com/madebygps"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300"
            >
              Gwyneth Peña-Siguenza
            </a>
            {" & "}
            <a
              href="https://x.com/rishabincloud"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300"
            >
              Rishab Kumar
            </a>
            {" · "}
            <a
              href="https://creativecommons.org/licenses/by/4.0/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300"
            >
              Licensed under CC BY 4.0
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
