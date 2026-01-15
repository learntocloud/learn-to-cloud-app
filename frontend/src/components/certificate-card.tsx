"use client";

import { useState } from "react";
import type { Certificate } from "@/lib/types";

interface CertificateCardProps {
  certificate: Certificate;
}

const CERTIFICATE_TYPE_NAMES: Record<string, string> = {
  full_completion: "Full Program Completion",
  phase_0: "Phase 0: Starting from Zero",
  phase_1: "Phase 1: Linux & Bash",
  phase_2: "Phase 2: Programming & APIs",
  phase_3: "Phase 3: Cloud Platform Fundamentals",
  phase_4: "Phase 4: DevOps & Containers",
  phase_5: "Phase 5: Cloud Security",
};

export function CertificateCard({ certificate }: CertificateCardProps) {
  const [showPreview, setShowPreview] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const issuedDate = new Date(certificate.issued_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const verifyUrl = `${typeof window !== "undefined" ? window.location.origin : ""}/verify/${certificate.verification_code}`;
  const svgUrl = `/api/certificates/${certificate.id}/svg`;
  const pdfUrl = `/api/certificates/${certificate.id}/pdf`;

  const handleDownload = async (format: "pdf" | "svg") => {
    setIsDownloading(true);
    try {
      const url = format === "pdf" ? pdfUrl : svgUrl;
      const response = await fetch(url);
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `ltc-certificate-${certificate.verification_code}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
      console.error(`Failed to download certificate as ${format}:`, error);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleCopyVerifyLink = async () => {
    try {
      await navigator.clipboard.writeText(verifyUrl);
      // Could add a toast notification here
    } catch (error) {
      console.error("Failed to copy link:", error);
    }
  };

  return (
    <div className="bg-white dark:bg-slate-800/50 rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden">
      <div className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {CERTIFICATE_TYPE_NAMES[certificate.certificate_type] || certificate.certificate_type}
            </h3>
            <p className="text-gray-600 dark:text-slate-400 text-sm">
              Issued to <span className="text-gray-900 dark:text-white">{certificate.recipient_name}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xl">
              {certificate.certificate_type === "full_completion" ? "🏆" : "📜"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
          <div>
            <span className="text-gray-500 dark:text-slate-500">Issued</span>
            <p className="text-gray-900 dark:text-white">{issuedDate}</p>
          </div>
          <div>
            <span className="text-gray-500 dark:text-slate-500">Phases Completed</span>
            <p className="text-gray-900 dark:text-white">
              {certificate.phases_completed} / {certificate.total_phases}
            </p>
          </div>
        </div>

        <div className="mb-4">
          <span className="text-gray-500 dark:text-slate-500 text-sm">Verification Code</span>
          <p className="font-mono text-amber-600 dark:text-amber-400 text-sm">{certificate.verification_code}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="px-4 py-2 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 text-gray-700 dark:text-white rounded-lg text-sm transition-colors"
          >
            {showPreview ? "Hide Preview" : "Preview"}
          </button>
          <button
            onClick={() => handleDownload("pdf")}
            disabled={isDownloading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isDownloading ? "Downloading..." : "Download PDF"}
          </button>
          <button
            onClick={handleCopyVerifyLink}
            className="px-4 py-2 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 text-gray-700 dark:text-white rounded-lg text-sm transition-colors"
          >
            Copy Verify Link
          </button>
        </div>
      </div>

      {showPreview && (
        <div className="border-t border-gray-200 dark:border-slate-700 p-4 bg-gray-50 dark:bg-slate-900/50">
          <img
            src={svgUrl}
            alt={`Certificate: ${certificate.recipient_name}`}
            className="w-full rounded-lg"
          />
        </div>
      )}
    </div>
  );
}
