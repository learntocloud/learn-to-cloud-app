"use client";

import Link from "next/link";
import { UserButton, SignInButton, useUser } from "@clerk/nextjs";

export function Navbar() {
  const { isSignedIn, isLoaded } = useUser();

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl">☁️</span>
              <span className="font-bold text-xl text-gray-900 dark:text-white">Learn to Cloud</span>
            </Link>
            <div className="hidden sm:ml-8 sm:flex sm:space-x-4">
              <Link
                href="/phases"
                className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-2 text-sm font-medium"
              >
                Phases
              </Link>
              {isSignedIn && (
                <Link
                  href="/dashboard"
                  className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-2 text-sm font-medium"
                >
                  Dashboard
                </Link>
              )}
            </div>
          </div>
          <div className="flex items-center">
            {isLoaded && (
              <>
                {isSignedIn ? (
                  <UserButton />
                ) : (
                  <SignInButton mode="modal">
                    <button className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
                      Sign In
                    </button>
                  </SignInButton>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
