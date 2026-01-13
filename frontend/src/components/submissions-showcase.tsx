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
  }
}

function getSubmissionTypeLabel(type: SubmissionType) {
  switch (type) {
    case "profile_readme":
      return "Profile README";
    case "repo_fork":
      return "Repository";
    case "deployed_app":
      return "Deployed App";
  }
}

function getPhaseColor(phaseId: number) {
  const colors = [
    "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
    "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
    "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
    "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
    "bg-pink-100 text-pink-700 dark:bg-pink-900/50 dark:text-pink-300",
  ];
  return colors[phaseId] || colors[0];
}

export function SubmissionsShowcase({ submissions }: SubmissionsShowcaseProps) {
  if (!submissions || submissions.length === 0) {
    return null;
  }

  // Group submissions by phase
  const groupedByPhase = submissions.reduce((acc, submission) => {
    const phase = submission.phase_id;
    if (!acc[phase]) {
      acc[phase] = [];
    }
    acc[phase].push(submission);
    return acc;
  }, {} as Record<number, PublicSubmission[]>);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-gray-700 dark:text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">
          Projects & Submissions
        </h2>
        <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
          {submissions.length} completed
        </span>
      </div>

      <div className="space-y-4">
        {Object.entries(groupedByPhase)
          .sort(([a], [b]) => Number(a) - Number(b))
          .map(([phaseId, phaseSubmissions]) => (
            <div key={phaseId}>
              <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                Phase {phaseId}
              </div>
              <div className="space-y-2">
                {phaseSubmissions.map((submission) => (
                  <a
                    key={submission.requirement_id}
                    href={submission.submitted_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors group"
                  >
                    <div className={`p-2 rounded-lg ${getPhaseColor(Number(phaseId))}`}>
                      {getSubmissionIcon(submission.submission_type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900 dark:text-white truncate group-hover:text-blue-600 dark:group-hover:text-blue-400">
                        {submission.name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                        <span>{getSubmissionTypeLabel(submission.submission_type)}</span>
                        {submission.validated_at && (
                          <>
                            <span>•</span>
                            <span>
                              Verified {new Date(submission.validated_at).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <svg
                      className="w-4 h-4 text-gray-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 shrink-0"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
