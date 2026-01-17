import { Link } from 'react-router-dom';
import { useUserCertificates, useCertificateEligibility, useGenerateCertificate } from '@/lib/hooks';
import { createApiClient } from '@/lib/api-client';
import { useAuth } from '@clerk/clerk-react';
import { useMemo, useState } from 'react';

function formatIssuedDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(textarea);
      return ok;
    } catch {
      return false;
    }
  }
}

function CopyRow({
  label,
  value,
  isLink,
}: {
  label: string;
  value: string;
  isLink?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyToClipboard(value);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-xs font-medium text-gray-600 dark:text-gray-400">{label}</div>
        {isLink ? (
          <a
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 block truncate font-mono text-sm text-blue-700 hover:underline dark:text-blue-300"
            title={value}
          >
            {value}
          </a>
        ) : (
          <div
            className="mt-1 truncate font-mono text-sm text-gray-900 dark:text-gray-100"
            title={value}
          >
            {value}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={handleCopy}
        className="inline-flex h-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white px-3 text-sm font-medium text-gray-800 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
        aria-label={`Copy ${label}`}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

export function CertificatesPage() {
  const { data: userCerts, isLoading } = useUserCertificates();
  const { data: eligibility } = useCertificateEligibility('full_completion');
  const generateMutation = useGenerateCertificate();
  const { getToken } = useAuth();
  const api = createApiClient(getToken);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await generateMutation.mutateAsync({ certificateType: 'full_completion', recipientName: 'Learner' });
    } catch (error) {
      console.error('Failed to generate certificate:', error);
    } finally {
      setGenerating(false);
    }
  };

  const hasCertificate = !!userCerts?.certificates?.length;
  const certificate = hasCertificate ? userCerts!.certificates[0] : null;
  const isEligible = eligibility?.is_eligible ?? false;

  const verificationCode = certificate?.verification_code ?? null;

  const verifyPath = useMemo(() => {
    if (!verificationCode) return null;
    return `/verify/${verificationCode}`;
  }, [verificationCode]);

  const verifyUrl = useMemo(() => {
    if (!verifyPath) return null;
    if (typeof window === 'undefined') return verifyPath;
    return `${window.location.origin}${verifyPath}`;
  }, [verifyPath]);

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="mb-6">
          <Link to="/dashboard" className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-sm">
            ← Back to Dashboard
          </Link>
        </nav>

        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          Your Certificates
        </h1>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : hasCertificate && certificate ? (
          <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="p-6 sm:p-8">
              <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex items-start gap-4">
                  <div className="grid h-12 w-12 place-items-center rounded-xl bg-blue-50 text-2xl dark:bg-blue-950/40">
                    🏆
                  </div>
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                      Learn to Cloud Completion Certificate
                    </h2>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      Issued {formatIssuedDate(certificate.issued_at)}
                    </p>
                  </div>
                </div>

                {verificationCode ? (
                  <div className="w-full sm:w-56">
                    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900/40">
                      <img
                        src={api.getVerifiedCertificatePngUrl(verificationCode, 2)}
                        alt="Certificate preview"
                        className="h-28 w-full rounded-lg bg-white object-contain dark:bg-gray-950"
                        loading="lazy"
                      />
                      <div className="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
                        Preview
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
                <a
                  href={
                    verificationCode
                      ? api.getVerifiedCertificatePdfUrl(verificationCode)
                      : api.getCertificatePdfUrl(certificate.id)
                  }
                  className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
                >
                  Download PDF
                </a>

                {verificationCode ? (
                  <a
                    href={api.getVerifiedCertificatePngUrl(verificationCode, 2)}
                    className="inline-flex items-center justify-center rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Download PNG
                  </a>
                ) : null}

                {verifyPath ? (
                  <Link
                    to={verifyPath}
                    className="inline-flex items-center justify-center rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Open Verify Page
                  </Link>
                ) : null}
              </div>

              <div className="mt-8 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  Verification
                </div>
                <div className="mt-3 space-y-4">
                  <CopyRow
                    label="Verification code"
                    value={verificationCode ?? ''}
                  />
                  {verifyUrl ? (
                    <CopyRow label="Share verify link" value={verifyUrl} isLink />
                  ) : null}
                </div>
                <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                  Anyone with the verify link can validate the certificate.
                </div>
              </div>
            </div>
          </div>
        ) : isEligible ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 text-center">
            <div className="text-5xl mb-4">🎉</div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Congratulations!
            </h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              You've completed all requirements. Generate your certificate now!
            </p>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {generating ? 'Generating...' : 'Generate Certificate'}
            </button>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="text-5xl mb-4 text-center">🎯</div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 text-center">
              Keep Going!
            </h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6 text-center">
              Complete all phases to earn your Learn to Cloud completion certificate.
            </p>

            {eligibility && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Progress:</p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {eligibility.phases_completed} of {eligibility.total_phases} phases completed ({eligibility.completion_percentage}%)
                </p>
              </div>
            )}

            <div className="mt-6 text-center">
              <Link
                to="/dashboard"
                className="text-blue-600 dark:text-blue-400 font-medium hover:underline"
              >
                Continue Learning →
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
