"use client";

import Link from "next/link";
import { SignUpButton, useUser } from "@clerk/nextjs";

/**
 * Hero CTA buttons that adapt based on auth state.
 * Client component to avoid blocking SSR with auth() call.
 */
export function HeroCTA() {
  const { isSignedIn, isLoaded } = useUser();

  // Show skeleton while Clerk loads to prevent layout shift
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
      <Link
        href="/dashboard"
        className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
      >
        Go to Dashboard →
      </Link>
    );
  }

  return (
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
  );
}
