import { useMemo, useState } from "react";
import { PhaseThemeData, PublicSubmission, SubmissionType } from "@/lib/types";

interface SubmissionsShowcaseProps {
  submissions: PublicSubmission[];
  phaseThemes?: Record<number, PhaseThemeData>;
}

function getSubmissionIcon(type: SubmissionType) {
  switch (type) {
    case "github_profile":
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
    case "code_analysis":
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5-6l3 3-3 3M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z" />
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

// Phase colors for visual differentiation (fallback when content themes are missing)
const PHASE_COLORS: Record<number, { bg: string; border: string; text: string; icon: string }> = {
  0: { bg: "bg-gray-50 dark:bg-gray-800/50", border: "border-gray-200 dark:border-gray-700", text: "text-gray-600 dark:text-gray-400", icon: "🌱" },
  1: { bg: "bg-blue-50 dark:bg-blue-900/20", border: "border-blue-200 dark:border-blue-800", text: "text-blue-600 dark:text-blue-400", icon: "🐧" },
  2: { bg: "bg-green-50 dark:bg-green-900/20", border: "border-green-200 dark:border-green-800", text: "text-green-600 dark:text-green-400", icon: "🐍" },
  3: { bg: "bg-purple-50 dark:bg-purple-900/20", border: "border-purple-200 dark:border-purple-800", text: "text-purple-600 dark:text-purple-400", icon: "☁️" },
  4: { bg: "bg-orange-50 dark:bg-orange-900/20", border: "border-orange-200 dark:border-orange-800", text: "text-orange-600 dark:text-orange-400", icon: "🚀" },
  5: { bg: "bg-pink-50 dark:bg-pink-900/20", border: "border-pink-200 dark:border-pink-800", text: "text-pink-600 dark:text-pink-400", icon: "🔧" },
  6: { bg: "bg-red-50 dark:bg-red-900/20", border: "border-red-200 dark:border-red-800", text: "text-red-600 dark:text-red-400", icon: "🔐" },
};

function getPhaseColors(phaseId: number, phaseThemes?: Record<number, PhaseThemeData>) {
  const theme = phaseThemes?.[phaseId];
  if (theme) {
    return {
      bg: theme.bg_class,
      border: theme.border_class,
      text: theme.text_class,
      icon: theme.icon,
    };
  }
  return PHASE_COLORS[phaseId] || PHASE_COLORS[0];
}

export function SubmissionsShowcase({ submissions, phaseThemes }: SubmissionsShowcaseProps) {
  const [showAll, setShowAll] = useState(false);
  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }),
    []
  );

  if (!submissions || submissions.length === 0) {
    return null;
  }

  // Filter out CTF token if fork exists (they'll be combined)
  const hasCTFToken = submissions.some(s => s.requirement_id === "linux-ctfs-token");
  const hasCTFFork = submissions.some(s => s.requirement_id === "linux-ctfs-fork");

  const filteredSubmissions = submissions.filter(s => {
    if (s.requirement_id === "linux-ctfs-token" && hasCTFFork) {
      return false;
    }
    return true;
  });

  const displayLimit = 4;
  const hasMore = filteredSubmissions.length > displayLimit;
  const displayedSubmissions = showAll ? filteredSubmissions : filteredSubmissions.slice(0, displayLimit);

  const formatValidatedAt = (value?: string | null) => {
    if (!value) {
      return null;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return dateFormatter.format(parsed);
  };

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
          const colors = getPhaseColors(submission.phase_id, phaseThemes);
          const showVerified = submission.requirement_id === "linux-ctfs-fork" && hasCTFToken;
          const description = submission.description || "Completed project submission";
          const validatedAt = formatValidatedAt(submission.validated_at);

          return (
            <a
              key={submission.requirement_id}
              href={submission.submitted_value}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`${submission.name} (opens in new tab)`}
              className={`block p-5 rounded-xl border ${colors.border} ${colors.bg} hover:shadow-md transition-all group`}
            >
              <div className="flex items-start gap-4">
                <div className={`shrink-0 ${colors.text} mt-0.5`}>
                  {getSubmissionIcon(submission.submission_type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-semibold text-gray-900 dark:text-white text-sm truncate group-hover:text-gray-600 dark:group-hover:text-gray-300">
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
                  <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-3">
                    {description}
                  </p>
                  <div className="flex items-center gap-2 mt-3">
                    <span className={`text-xs font-medium ${colors.text} bg-white/70 dark:bg-gray-900/40 border ${colors.border} px-2 py-0.5 rounded-full`}>
                      {colors.icon} Phase {submission.phase_id}
                    </span>
                    {validatedAt && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        Verified {validatedAt}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300">
                      Open link
                    </span>
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
          aria-label={showAll ? "Show fewer projects" : `Show ${filteredSubmissions.length - displayLimit} more projects`}
          className="w-full mt-3 py-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          {showAll ? "Show less" : `Show ${filteredSubmissions.length - displayLimit} more projects`}
        </button>
      )}
    </div>
  );
}
