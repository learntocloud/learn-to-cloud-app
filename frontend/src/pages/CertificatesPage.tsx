import { Link } from 'react-router-dom';
import { useUserCertificates, useCertificateEligibility, useGenerateCertificate } from '@/lib/hooks';
import { createApiClient } from '@/lib/api-client';
import { useAuth } from '@clerk/clerk-react';
import { useState } from 'react';

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

  if (isLoading) {
    return (
      <div className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </div>
      </div>
    );
  }

  const hasCertificate = userCerts && userCerts.certificates && userCerts.certificates.length > 0;
  const certificate = hasCertificate ? userCerts.certificates[0] : null;
  const isEligible = eligibility?.is_eligible ?? false;

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

        {hasCertificate && certificate ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center gap-4 mb-4">
              <div className="text-4xl">🏆</div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                  Learn to Cloud Completion Certificate
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Issued: {new Date(certificate.issued_at).toLocaleDateString()}
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <a
                href={api.getCertificateSvgUrl(certificate.id)}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                View Certificate
              </a>
              <a
                href={api.getCertificatePdfUrl(certificate.id)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Download PDF
              </a>
            </div>

            <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                <strong>Verification Code:</strong> {certificate.verification_code}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
                Share this link to verify: {window.location.origin}/verify/{certificate.verification_code}
              </p>
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
