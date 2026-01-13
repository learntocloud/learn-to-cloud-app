"use client";

import { useState } from "react";

interface DashboardGreetingProps {
  userName?: string;
  aiGreeting?: string;
  currentStreak: number;
}

export function DashboardGreeting({ 
  userName, 
  aiGreeting, 
  currentStreak 
}: DashboardGreetingProps) {
  const [showFullGreeting, setShowFullGreeting] = useState(false);

  // Default greeting if no AI greeting is available
  const defaultGreeting = `Welcome back${userName ? `, ${userName}` : ""}! 👋`;
  
  // If AI greeting is too long, truncate it
  const MAX_PREVIEW_LENGTH = 150;
  const hasLongGreeting = aiGreeting && aiGreeting.length > MAX_PREVIEW_LENGTH;
  const displayGreeting = aiGreeting 
    ? (hasLongGreeting && !showFullGreeting 
        ? aiGreeting.slice(0, MAX_PREVIEW_LENGTH) + "..." 
        : aiGreeting)
    : null;

  return (
    <div className="mb-8">
      {/* Main Greeting */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            {defaultGreeting}
          </h1>
          
          {/* AI-generated personalized message */}
          {displayGreeting && (
            <div className="mt-3 p-4 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20 rounded-lg border border-purple-100 dark:border-purple-800/50">
              <div className="flex items-start gap-3">
                <span className="text-xl">✨</span>
                <div className="flex-1">
                  <p className="text-gray-700 dark:text-gray-300 text-sm italic">
                    {displayGreeting}
                  </p>
                  {hasLongGreeting && (
                    <button
                      onClick={() => setShowFullGreeting(!showFullGreeting)}
                      className="text-purple-600 dark:text-purple-400 text-xs mt-1 hover:underline"
                    >
                      {showFullGreeting ? "Show less" : "Read more"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
          
          <p className="text-gray-600 dark:text-gray-300 mt-2">
            Track your progress through Learn to Cloud
          </p>
        </div>

        {/* Streak Badge */}
        {currentStreak > 0 && (
          <div className="flex-shrink-0">
            <div className="flex items-center gap-2 px-4 py-2 bg-orange-100 dark:bg-orange-900/30 rounded-full">
              <span className="text-2xl">🔥</span>
              <div className="text-right">
                <div className="text-lg font-bold text-orange-600 dark:text-orange-400">
                  {currentStreak}
                </div>
                <div className="text-xs text-orange-600/70 dark:text-orange-400/70">
                  day streak
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
