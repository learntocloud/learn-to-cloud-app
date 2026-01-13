"use client";

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

// Phase colors and icons for visual differentiation
const PHASE_STYLES: Record<number, { color: string; icon: string; borderColor: string }> = {
  0: { 
    color: "text-gray-600 dark:text-gray-400", 
    borderColor: "border-gray-300 dark:border-gray-600",
    icon: "🌱" 
  },
  1: { 
    color: "text-blue-600 dark:text-blue-400", 
    borderColor: "border-blue-300 dark:border-blue-600",
    icon: "🐧" 
  },
  2: { 
    color: "text-green-600 dark:text-green-400", 
    borderColor: "border-green-300 dark:border-green-600",
    icon: "🐍" 
  },
  3: { 
    color: "text-purple-600 dark:text-purple-400", 
    borderColor: "border-purple-300 dark:border-purple-600",
    icon: "☁️" 
  },
  4: { 
    color: "text-orange-600 dark:text-orange-400", 
    borderColor: "border-orange-300 dark:border-orange-600",
    icon: "🚀" 
  },
  5: { 
    color: "text-pink-600 dark:text-pink-400", 
    borderColor: "border-pink-300 dark:border-pink-600",
    icon: "🔐" 
  },
};

function getPhaseStyle(phaseId: number) {
  return PHASE_STYLES[phaseId] || PHASE_STYLES[0];
}

// Submissions that should be combined (CTF token links to fork)
const CTF_RELATED_IDS = ["linux_ctf_token", "linux_ctfs_fork"];

export function SubmissionsShowcase({ submissions }: SubmissionsShowcaseProps) {
  if (!submissions || submissions.length === 0) {
    return null;
  }

  // Check if both CTF submissions exist
  const hasCTFToken = submissions.some(s => s.requirement_id === "linux_ctf_token");
  const hasCTFFork = submissions.some(s => s.requirement_id === "linux_ctfs_fork");
  const ctfFork = submissions.find(s => s.requirement_id === "linux_ctfs_fork");
  
  // Filter out CTF token if fork exists (they'll be combined)
  const filteredSubmissions = submissions.filter(s => {
    if (s.requirement_id === "linux_ctf_token" && hasCTFFork) {
      return false; // Skip token, we'll show it combined with fork
    }
    return true;
  });

  // Group submissions by phase
  const groupedByPhase = filteredSubmissions.reduce((acc, submission) => {
    const phase = submission.phase_id;
    if (!acc[phase]) {
      acc[phase] = [];
    }
    acc[phase].push(submission);
    return acc;
  }, {} as Record<number, PublicSubmission[]>);

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          Projects
        </h2>
        <span className="text-sm text-gray-400 dark:text-gray-500">
          {filteredSubmissions.length}
        </span>
      </div>

      <div className="space-y-2">
        {Object.entries(groupedByPhase)
          .sort(([a], [b]) => Number(a) - Number(b))
          .map(([phaseId, phaseSubmissions]) => {
            const phaseStyle = getPhaseStyle(Number(phaseId));
            
            return (
              <div key={phaseId} className="space-y-1">
                {phaseSubmissions.map((submission) => {
                  // Check if this is the CTF fork that should show verified badge
                  const showVerified = submission.requirement_id === "linux_ctfs_fork" && hasCTFToken;
                  
                  return (
                    <a
                      key={submission.requirement_id}
                      href={submission.submitted_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`flex items-center gap-3 py-2.5 px-3 -mx-3 rounded-lg border-l-2 ${phaseStyle.borderColor} hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group`}
                    >
                      <div className={phaseStyle.color}>
                        {getSubmissionIcon(submission.submission_type)}
                      </div>
                      <div className="flex-1 min-w-0 flex items-center gap-2">
                        <span className="text-gray-900 dark:text-white group-hover:text-gray-600 dark:group-hover:text-gray-300 truncate">
                          {submission.name}
                        </span>
                        {showVerified && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 text-xs rounded-full">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            CTF
                          </span>
                        )}
                      </div>
                      <span className={`text-xs font-medium ${phaseStyle.color}`}>
                        {phaseStyle.icon} Phase {phaseId}
                      </span>
                      <svg
                        className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-gray-400 shrink-0"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  );
                })}
              </div>
            );
          })}
      </div>
    </div>
  );
}
