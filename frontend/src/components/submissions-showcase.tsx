"use client";

import { useState } from "react";
import { PublicSubmission, SubmissionType } from "@/lib/types";

interface SubmissionsShowcaseProps {
  submissions: PublicSubmission[];
}

function getSubmissionIcon(type: SubmissionType) {
  switch (type) {
    case "profile_readme":
      return (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
        </svg>
      );
    case "repo_fork":
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
        </svg>
      );
    case "deployed_app":
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    default:
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      );
  }
}

// Descriptions for each project type
const PROJECT_DESCRIPTIONS: Record<string, string> = {
  "phase0-github-profile": "Demonstrates account setup and version control basics",
  "phase1-profile-readme": "Showcases Markdown skills and personal branding",
  "phase1-linux-ctfs-fork": "Completed hands-on Linux command line challenges",
  "phase1-linux-ctf-token": "Verified completion of all 18 CTF challenges",
  "phase2-journal-starter-fork": "Built a full-stack API with FastAPI & PostgreSQL",
  "phase3-copilot-demo": "Demonstrates AI-assisted development workflow",
  "phase4-deployed-journal-api": "Successfully deployed application to the cloud",
  "phase5-dockerfile": "Containerized application with Docker",
  "phase5-cicd-pipeline": "Automated build, test, and deployment pipeline",
  "phase6-security-scan": "Implemented security scanning and vulnerability management",
};

// Phase colors for visual differentiation
const PHASE_COLORS: Record<number, { bg: string; border: string; text: string; icon: string }> = {
  0: { bg: "bg-gray-50 dark:bg-gray-800/50", border: "border-gray-200 dark:border-gray-700", text: "text-gray-600 dark:text-gray-400", icon: "🌱" },
  1: { bg: "bg-blue-50 dark:bg-blue-900/20", border: "border-blue-200 dark:border-blue-800", text: "text-blue-600 dark:text-blue-400", icon: "🐧" },
  2: { bg: "bg-green-50 dark:bg-green-900/20", border: "border-green-200 dark:border-green-800", text: "text-green-600 dark:text-green-400", icon: "🐍" },
  3: { bg: "bg-purple-50 dark:bg-purple-900/20", border: "border-purple-200 dark:border-purple-800", text: "text-purple-600 dark:text-purple-400", icon: "☁️" },
  4: { bg: "bg-orange-50 dark:bg-orange-900/20", border: "border-orange-200 dark:border-orange-800", text: "text-orange-600 dark:text-orange-400", icon: "🚀" },
  5: { bg: "bg-pink-50 dark:bg-pink-900/20", border: "border-pink-200 dark:border-pink-800", text: "text-pink-600 dark:text-pink-400", icon: "🔧" },
  6: { bg: "bg-red-50 dark:bg-red-900/20", border: "border-red-200 dark:border-red-800", text: "text-red-600 dark:text-red-400", icon: "🔐" },
};

function getPhaseColors(phaseId: number) {
  return PHASE_COLORS[phaseId] || PHASE_COLORS[0];
}

export function SubmissionsShowcase({ submissions }: SubmissionsShowcaseProps) {
  const [showAll, setShowAll] = useState(false);
  
  if (!submissions || submissions.length === 0) {
    return null;
  }

  // Filter out CTF token if fork exists (they'll be combined)
  const hasCTFToken = submissions.some(s => s.requirement_id === "phase1-linux-ctf-token");
  const hasCTFFork = submissions.some(s => s.requirement_id === "phase1-linux-ctfs-fork");
  
  const filteredSubmissions = submissions.filter(s => {
    if (s.requirement_id === "phase1-linux-ctf-token" && hasCTFFork) {
      return false;
    }
    return true;
  });

  const displayLimit = 4;
  const hasMore = filteredSubmissions.length > displayLimit;
  const displayedSubmissions = showAll ? filteredSubmissions : filteredSubmissions.slice(0, displayLimit);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Projects
          </h2>
          <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-full">
            {filteredSubmissions.length}
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {displayedSubmissions.map((submission) => {
          const colors = getPhaseColors(submission.phase_id);
          const showVerified = submission.requirement_id === "phase1-linux-ctfs-fork" && hasCTFToken;
          const description = PROJECT_DESCRIPTIONS[submission.requirement_id] || "Completed project submission";
          
          return (
            <a
              key={submission.requirement_id}
              href={submission.submitted_url}
              target="_blank"
              rel="noopener noreferrer"
              className={`block p-4 rounded-xl border ${colors.border} ${colors.bg} hover:shadow-md transition-all group`}
            >
              <div className="flex items-start gap-3">
                <div className={`shrink-0 ${colors.text}`}>
                  {getSubmissionIcon(submission.submission_type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-gray-900 dark:text-white text-sm truncate group-hover:text-gray-600 dark:group-hover:text-gray-300">
                      {submission.name}
                    </span>
                    {showVerified && (
                      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 text-xs rounded-full shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        CTF
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                    {description}
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <span className={`text-xs font-medium ${colors.text}`}>
                      {colors.icon} Phase {submission.phase_id}
                    </span>
                    <svg
                      className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-gray-400 shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </div>
                </div>
              </div>
            </a>
          );
        })}
      </div>

      {hasMore && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full mt-3 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          {showAll ? "Show less" : `Show ${filteredSubmissions.length - displayLimit} more projects`}
        </button>
      )}
    </div>
  );
}
