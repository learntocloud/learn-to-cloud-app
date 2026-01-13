import { verifyCertificate, getVerifiedCertificatePdfUrl, getVerifiedCertificateSvgUrl } from "@/lib/api";
import Link from "next/link";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

interface VerifyPageProps {
  params: Promise<{ code: string }>;
}

export async function generateMetadata({ params }: VerifyPageProps) {
  const { code } = await params;
  const result = await verifyCertificate(code);
  
  if (result.is_valid && result.certificate) {
    return {
      title: `Certificate for ${result.certificate.recipient_name} | Learn to Cloud`,
      description: `Verified Learn to Cloud certificate issued to ${result.certificate.recipient_name}`,
    };
  }
  
  return {
    title: "Certificate Verification | Learn to Cloud",
    description: "Verify a Learn to Cloud completion certificate",
  };
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

function VerifiedBadge() {
  return (
    <div className="relative">
      {/* Glow effect */}
      <div className="absolute inset-0 blur-xl bg-emerald-500/30 rounded-full" />
      <svg className="relative w-20 h-20" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="30" className="fill-emerald-100 dark:fill-emerald-500/30 stroke-emerald-500 dark:stroke-emerald-400" strokeWidth="2" />
        <path
          d="M20 32L28 40L44 24"
          className="stroke-emerald-600 dark:stroke-emerald-400"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function InvalidBadge() {
  return (
    <svg className="w-16 h-16" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" className="fill-red-100 dark:fill-red-500/20 stroke-red-500" strokeWidth="2" />
      <path
        d="M24 24L40 40M40 24L24 40"
        className="stroke-red-500 dark:stroke-red-400"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ShieldIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
        className="fill-current"
        opacity="0.2"
      />
      <path
        d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
        className="stroke-current"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <path
        d="M9 12l2 2 4-4"
        className="stroke-current"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default async function VerifyPage({ params }: VerifyPageProps) {
  const { code } = await params;
  const result = await verifyCertificate(code);

  return (
    <div className="min-h-screen py-8 sm:py-12">
      <div className="max-w-2xl mx-auto px-4 sm:px-6">
        {/* Back Link */}
        <Link 
          href="/" 
          className="inline-flex items-center gap-2 text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white text-sm mb-8 transition-colors group"
        >
          <svg className="w-4 h-4 transition-transform group-hover:-translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Learn to Cloud
        </Link>

        {result.is_valid && result.certificate ? (
          <div className="space-y-6">
            {/* Verification Status Card */}
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-50 via-emerald-50/80 to-white dark:from-slate-800 dark:via-slate-800/95 dark:to-slate-900 border border-emerald-200 dark:border-emerald-500/30 p-8 shadow-lg shadow-emerald-500/10 dark:shadow-emerald-500/5">
              {/* Background Pattern */}
              <div className="absolute inset-0 opacity-10">
                <div className="absolute top-4 right-4">
                  <ShieldIcon className="w-32 h-32 text-emerald-500 dark:text-emerald-400" />
                </div>
              </div>
              
              {/* Success Glow Effect */}
              <div className="absolute inset-0 bg-gradient-to-t from-emerald-500/5 dark:from-emerald-500/10 via-transparent to-transparent pointer-events-none" />
              
              <div className="relative flex flex-col items-center text-center">
                <VerifiedBadge />
                <h1 className="mt-4 text-2xl font-bold text-emerald-900 dark:text-emerald-50">
                  Verified Certificate
                </h1>
                <p className="mt-2 text-emerald-600 dark:text-emerald-400 font-semibold text-lg">
                  This certificate is authentic and valid
                </p>
              </div>
            </div>

            {/* Recipient Card */}
            <div className="rounded-2xl bg-white dark:bg-slate-800/60 backdrop-blur border border-gray-200 dark:border-slate-700/50 p-6">
              <div className="flex items-center gap-4">
                <div className="flex-shrink-0 w-14 h-14 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
                  <span className="text-2xl font-bold text-white dark:text-slate-900">
                    {result.certificate.recipient_name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-500 font-medium">Awarded to</p>
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                    {result.certificate.recipient_name}
                  </h2>
                </div>
              </div>
            </div>

            {/* Details Grid */}
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-xl bg-white dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50 p-4">
                <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400 font-medium mb-1">Certificate</p>
                <p className="text-gray-900 dark:text-slate-100 font-semibold">
                  {CERTIFICATE_TYPE_NAMES[result.certificate.certificate_type] || result.certificate.certificate_type}
                </p>
              </div>
              <div className="rounded-xl bg-white dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50 p-4">
                <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400 font-medium mb-1">Issued</p>
                <p className="text-gray-900 dark:text-slate-100 font-semibold">
                  {new Date(result.certificate.issued_at).toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                  })}
                </p>
              </div>
              <div className="rounded-xl bg-white dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50 p-4">
                <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400 font-medium mb-1">Progress</p>
                <div className="flex items-center gap-2">
                  <p className="text-gray-900 dark:text-slate-100 font-semibold">
                    {result.certificate.topics_completed}/{result.certificate.total_topics} topics
                  </p>
                  {result.certificate.topics_completed === result.certificate.total_topics && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 font-medium">
                      100%
                    </span>
                  )}
                </div>
              </div>
              <div className="rounded-xl bg-white dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50 p-4">
                <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400 font-medium mb-1">Verification</p>
                <p className="font-mono text-sm text-amber-600 dark:text-amber-300 break-all font-semibold">
                  {result.certificate.verification_code}
                </p>
              </div>
            </div>

            {/* Certificate Preview */}
            <div className="rounded-2xl bg-white dark:bg-slate-800/60 backdrop-blur border border-gray-200 dark:border-slate-700/50 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-slate-700/50 flex items-center justify-between">
                <h3 className="font-semibold text-gray-900 dark:text-white">Certificate Preview</h3>
                <div className="flex items-center gap-2">
                  <a
                    href={getVerifiedCertificatePdfUrl(code)}
                    download={`${result.certificate.recipient_name}-certificate.pdf`}
                    className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download PDF
                  </a>
                </div>
              </div>
              <div className="p-4 sm:p-6 bg-gradient-to-b from-gray-50 dark:from-slate-900/50 to-gray-100/50 dark:to-slate-800/30">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={getVerifiedCertificateSvgUrl(code)}
                  alt={`Certificate for ${result.certificate.recipient_name}`}
                  className="w-full rounded-xl shadow-2xl shadow-black/10 dark:shadow-black/20"
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl bg-gradient-to-br from-red-50 dark:from-red-500/10 via-red-50/50 dark:via-red-500/5 to-white dark:to-transparent border border-red-200 dark:border-red-500/20 p-8">
            <div className="flex flex-col items-center text-center">
              <InvalidBadge />
              <h1 className="mt-4 text-2xl font-bold text-gray-900 dark:text-white">
                Certificate Not Found
              </h1>
              <p className="mt-2 text-red-600 dark:text-red-400 font-medium max-w-md">
                {result.message}
              </p>
              <div className="mt-6 px-4 py-3 rounded-xl bg-gray-100 dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50">
                <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-500 font-medium mb-1">Verification Code</p>
                <p className="font-mono text-sm text-gray-700 dark:text-slate-300">{code}</p>
              </div>
              <Link
                href="/"
                className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gray-200 dark:bg-slate-700 hover:bg-gray-300 dark:hover:bg-slate-600 text-gray-900 dark:text-white font-medium transition-colors"
              >
                Return to Learn to Cloud
              </Link>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-10 pt-6 border-t border-gray-200 dark:border-slate-800 text-center">
          <div className="inline-flex items-center gap-2 text-gray-500 dark:text-slate-500 text-sm">
            <ShieldIcon className="w-4 h-4 text-gray-400 dark:text-slate-600" />
            Certificates verified by Learn to Cloud
          </div>
          <p className="mt-3 text-gray-500 dark:text-slate-600 text-sm">
            Want to earn your own certificate?{" "}
            <Link href="/" className="text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors">
              Start learning →
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
