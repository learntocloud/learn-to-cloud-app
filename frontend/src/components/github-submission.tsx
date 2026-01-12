"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import type { GitHubRequirement, GitHubSubmission, GitHubValidationResult } from "@/lib/types";

interface GitHubSubmissionFormProps {
  requirements: GitHubRequirement[];
  submissions: GitHubSubmission[];
  githubUsername: string | null;
  onSubmissionSuccess?: () => void;
}

// In dev containers/Codespaces, use same-origin proxy (Next.js rewrites /api/* to backend)
// In production, use the explicit API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const isUsingProxy = !API_URL || API_URL.includes('localhost') || API_URL.includes('127.0.0.1');

function getApiUrl(path: string): string {
  return isUsingProxy ? path : `${API_URL}${path}`;
}

export function GitHubSubmissionForm({
  requirements,
  submissions,
  githubUsername,
  onSubmissionSuccess,
}: GitHubSubmissionFormProps) {
  const { getToken } = useAuth();
  const [urls, setUrls] = useState<Record<string, string>>(() => {
    // Pre-fill with existing submissions
    const initial: Record<string, string> = {};
    for (const sub of submissions) {
      initial[sub.requirement_id] = sub.submitted_url;
    }
    return initial;
  });
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, GitHubValidationResult | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const getSubmissionForRequirement = (requirementId: string): GitHubSubmission | undefined => {
    return submissions.find((s) => s.requirement_id === requirementId);
  };

  const handleSubmit = async (requirementId: string) => {
    const url = urls[requirementId]?.trim();
    if (!url) {
      setErrors((prev) => ({ ...prev, [requirementId]: "Please enter a URL" }));
      return;
    }

    setLoading((prev) => ({ ...prev, [requirementId]: true }));
    setErrors((prev) => ({ ...prev, [requirementId]: "" }));
    setResults((prev) => ({ ...prev, [requirementId]: null }));

    try {
      const token = await getToken();
      const res = await fetch(getApiUrl("/api/github/submit"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          requirement_id: requirementId,
          submitted_url: url,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setErrors((prev) => ({
          ...prev,
          [requirementId]: data.detail || "Failed to validate submission",
        }));
        return;
      }

      setResults((prev) => ({ ...prev, [requirementId]: data }));
      
      if (data.is_valid && onSubmissionSuccess) {
        onSubmissionSuccess();
      }
    } catch {
      setErrors((prev) => ({
        ...prev,
        [requirementId]: "Network error. Please try again.",
      }));
    } finally {
      setLoading((prev) => ({ ...prev, [requirementId]: false }));
    }
  };

  // Check if any requirements need GitHub username
  const hasGitHubRequirements = requirements.some(
    (r) => r.submission_type === "profile_readme" || r.submission_type === "repo_fork"
  );

  if (!githubUsername && hasGitHubRequirements) {
    return (
      <div className="bg-yellow-50 dark:bg-yellow-900/30 rounded-lg border border-yellow-200 dark:border-yellow-800 p-6">
        <h3 className="text-lg font-semibold text-yellow-800 dark:text-yellow-200 mb-2">
          ⚠️ GitHub Account Required
        </h3>
        <p className="text-yellow-700 dark:text-yellow-300 mb-4">
          To submit your hands-on work, you need to sign in with GitHub. Please sign out and sign back in using your GitHub account.
        </p>
        <p className="text-sm text-yellow-600 dark:text-yellow-400">
          This allows us to verify that the GitHub repositories you submit actually belong to you.
        </p>
      </div>
    );
  }

  if (requirements.length === 0) {
    return null;
  }

  // Check if this phase has any deployed app requirements
  const hasDeployedAppReqs = requirements.some((r) => r.submission_type === "deployed_app");

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
        🔗 Hands-On Verification
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
        {hasDeployedAppReqs && !hasGitHubRequirements
          ? "Submit the URL of your deployed application to verify you've completed the hands-on work."
          : hasDeployedAppReqs && hasGitHubRequirements
          ? "Submit links to your GitHub repositories or deployed applications to verify you've completed the hands-on work."
          : "Submit links to your GitHub repositories to verify you've completed the hands-on work."}
        {githubUsername && hasGitHubRequirements && (
          <>
            {" "}Your GitHub username: <span className="font-mono text-blue-600 dark:text-blue-400">@{githubUsername}</span>
          </>
        )}
      </p>

      <div className="space-y-6">
        {requirements.map((req) => {
          const existingSubmission = getSubmissionForRequirement(req.id);
          const result = results[req.id];
          const error = errors[req.id];
          const isLoading = loading[req.id];
          const isValidated = existingSubmission?.is_validated || result?.is_valid;

          return (
            <div
              key={req.id}
              className={`p-4 rounded-lg border ${
                isValidated
                  ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800"
                  : "bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600"
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-medium text-gray-900 dark:text-white flex items-center gap-2">
                    {req.name}
                    {isValidated && (
                      <span className="text-green-600 dark:text-green-400 text-sm">✓ Verified</span>
                    )}
                  </h4>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                    {req.description}
                  </p>
                </div>
              </div>

              {req.example_url && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  Example: <code className="text-blue-600 dark:text-blue-400">{req.example_url}</code>
                </p>
              )}

              <div className="mt-4 flex gap-2">
                <input
                  type="url"
                  placeholder={
                    req.submission_type === "deployed_app"
                      ? "https://your-app.azurewebsites.net"
                      : `https://github.com/${githubUsername}/...`
                  }
                  value={urls[req.id] || ""}
                  onChange={(e) => setUrls((prev) => ({ ...prev, [req.id]: e.target.value }))}
                  disabled={isLoading}
                  className={`flex-1 px-3 py-2 text-sm rounded-lg border ${
                    error
                      ? "border-red-300 dark:border-red-600"
                      : "border-gray-300 dark:border-gray-600"
                  } bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50`}
                />
                <button
                  onClick={() => handleSubmit(req.id)}
                  disabled={isLoading}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? "Validating..." : isValidated ? "Re-verify" : "Verify"}
                </button>
              </div>

              {/* Error message */}
              {error && (
                <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
              )}

              {/* Result message */}
              {result && (
                <div
                  className={`mt-3 p-3 rounded-lg text-sm ${
                    result.is_valid
                      ? "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200"
                      : "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200"
                  }`}
                >
                  <p className="font-medium">{result.is_valid ? "✓ " : "✗ "}{result.message}</p>
                  {!result.is_valid && !result.username_match && req.submission_type !== "deployed_app" && (
                    <p className="mt-1 text-xs opacity-80">
                      Make sure the repository belongs to your GitHub account (@{githubUsername})
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
