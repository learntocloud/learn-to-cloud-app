import { useParams, Link } from 'react-router-dom';
import { useVerifyCertificate } from '@/lib/hooks';
import { createApiClient } from '@/lib/api-client';
import { useAuth } from '@clerk/clerk-react';

export function VerifyPage() {
  const { code } = useParams<{ code: string }>();
  const { getToken } = useAuth();
  const api = createApiClient(getToken);
  const { data: verification, isLoading, error } = useVerifyCertificate(code || '');

  // No code provided
  if (!code) {
    return (
      <div className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              Verify a Certificate
            </h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              Enter a verification code in the URL to verify a certificate.
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Example: /verify/ABC123
            </p>
          </div>
        </div>
      </div>
    );
  }

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

  if (error || !verification || !verification.is_valid || !verification.certificate) {
    return (
      <div className="min-h-screen py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-red-200 dark:border-red-800 p-8 text-center">
            <div className="text-6xl mb-4">❌</div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              Invalid Certificate
            </h1>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              This certificate code is invalid or has been revoked.
            </p>
            <Link
              to="/"
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Go Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const cert = verification.certificate;

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-emerald-200 dark:border-emerald-800 p-8">
          {/* Verified Badge */}
          <div className="flex items-center justify-center gap-3 mb-6">
            <div className="p-2 bg-emerald-100 dark:bg-emerald-900/50 rounded-full">
              <svg className="w-8 h-8 text-emerald-600 dark:text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-emerald-700 dark:text-emerald-300">
                Verified Certificate
              </h1>
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                This certificate is authentic and valid
              </p>
            </div>
          </div>

          {/* Certificate Details */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <div className="text-center mb-6">
              <p className="text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                Awarded to
              </p>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                {cert.recipient_name}
              </h2>
            </div>

            <div className="text-center mb-6">
              <p className="text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                For completing
              </p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">
                {cert.certificate_type === 'full_completion' 
                  ? 'Learn to Cloud Full Curriculum'
                  : cert.certificate_type}
              </p>
            </div>

            <div className="flex justify-center gap-8 text-sm text-gray-600 dark:text-gray-400">
              <div>
                <span className="font-medium">Issued:</span>{' '}
                {new Date(cert.issued_at).toLocaleDateString()}
              </div>
              <div>
                <span className="font-medium">Code:</span> {cert.verification_code}
              </div>
            </div>
          </div>

          {/* View/Download Links */}
          <div className="mt-8 flex justify-center gap-4">
            <a
              href={api.getVerifiedCertificateSvgUrl(code)}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              View Certificate
            </a>
            <a
              href={api.getVerifiedCertificatePdfUrl(code)}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              Download PDF
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
