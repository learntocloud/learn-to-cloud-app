"use client";

import { useState } from "react";
import type { CertificateEligibility } from "@/lib/types";

interface CertificateEligibilityCardProps {
  eligibility: CertificateEligibility;
  userName: string;
}

export function CertificateEligibilityCard({ eligibility, userName }: CertificateEligibilityCardProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [recipientName, setRecipientName] = useState(userName);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleGenerate = async () => {
    if (!eligibility.is_eligible) return;
    if (recipientName.trim().length < 2) {
      setError("Please enter your name (at least 2 characters)");
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      const response = await fetch("/api/certificates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          certificate_type: eligibility.certificate_type,
          recipient_name: recipientName.trim(),
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to generate certificate");
      }

      setSuccess(true);
      // Reload to show the new certificate
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate certificate");
    } finally {
      setIsGenerating(false);
    }
  };

  const progressPercentage = eligibility.completion_percentage;

  return (
    <div className="bg-white dark:bg-slate-800/50 rounded-xl border border-gray-200 dark:border-slate-700 p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {eligibility.is_eligible ? "Ready to Claim!" : "Keep Going!"}
          </h3>
          <p className="text-gray-600 dark:text-slate-400 text-sm">{eligibility.message}</p>
        </div>
        <span className="text-3xl">{eligibility.is_eligible ? "🎉" : "📚"}</span>
      </div>

      {/* Progress Bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-600 dark:text-slate-400">Progress</span>
          <span className="text-gray-900 dark:text-white font-medium">
            {eligibility.topics_completed} / {eligibility.total_topics} topics ({progressPercentage}%)
          </span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
          <div
            className={`h-3 rounded-full transition-all duration-500 ${
              eligibility.is_eligible ? "bg-green-500" : "bg-blue-500"
            }`}
            style={{ width: `${Math.min(progressPercentage, 100)}%` }}
          />
        </div>
        {!eligibility.is_eligible && (
          <p className="text-gray-500 dark:text-slate-500 text-xs mt-2">
            Need 100% completion ({eligibility.total_topics} topics) to earn this certificate
          </p>
        )}
      </div>

      {eligibility.is_eligible && !eligibility.already_issued && (
        <div className="space-y-4">
          <div>
            <label htmlFor="recipientName" className="block text-sm text-gray-600 dark:text-slate-400 mb-2">
              Name on Certificate
            </label>
            <input
              id="recipientName"
              type="text"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              placeholder="Your full name"
              className="w-full px-4 py-2 bg-gray-50 dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              maxLength={100}
            />
          </div>

          {error && (
            <div className="text-red-600 dark:text-red-400 text-sm bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg p-3">
              {error}
            </div>
          )}

          {success && (
            <div className="text-green-600 dark:text-green-400 text-sm bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-lg p-3">
              Certificate generated successfully! Reloading...
            </div>
          )}

          <button
            onClick={handleGenerate}
            disabled={isGenerating || success}
            className="w-full px-4 py-3 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? "Generating..." : "🏆 Generate Certificate"}
          </button>
        </div>
      )}

      {eligibility.already_issued && (
        <div className="text-gray-600 dark:text-slate-400 text-sm bg-gray-100 dark:bg-slate-700/50 rounded-lg p-3">
          ✓ Certificate already issued. Check your certificates above.
        </div>
      )}
    </div>
  );
}
