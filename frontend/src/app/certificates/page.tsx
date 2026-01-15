import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { getUserCertificates, getCertificateEligibility, getDashboard } from "@/lib/api";
import { CertificateCard } from "@/components/certificate-card";
import { CertificateEligibilityCard } from "@/components/certificate-eligibility";
import Link from "next/link";

// Disable static generation - fetch data at runtime
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Certificates | Learn to Cloud",
  description: "View and download your Learn to Cloud program completion certificate",
};

export default async function CertificatesPage() {
  const { userId } = await auth();
  
  if (!userId) {
    redirect("/sign-in");
  }

  const [certificates, dashboard, fullCompletionEligibility] = await Promise.all([
    getUserCertificates(),
    getDashboard(),
    getCertificateEligibility("full_completion").catch(() => ({
      is_eligible: false,
      certificate_type: "full_completion",
      phases_completed: 0,
      total_phases: 7,
      completion_percentage: 0,
      already_issued: false,
      existing_certificate_id: null,
      message: "Complete the program to earn your certificate",
    })),
  ]);

  const issuedCertificates = certificates.certificates;
  const hasFullCompletion = issuedCertificates.some(c => c.certificate_type === "full_completion");

  return (
    <div className="min-h-screen py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <Link 
            href="/dashboard" 
            className="text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 text-sm mb-4 inline-block"
          >
            ← Back to Dashboard
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Your Certificate</h1>
          <p className="text-gray-600 dark:text-slate-400">
            Complete all phases to earn your program completion certificate.
          </p>
        </div>

        {/* Full Completion Certificate Section */}
        <div className="mb-10">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <span className="text-2xl">🏆</span>
            Program Completion Certificate
          </h2>
          
          {hasFullCompletion ? (
            <div className="space-y-4">
              {issuedCertificates
                .filter(c => c.certificate_type === "full_completion")
                .map(cert => (
                  <CertificateCard key={cert.id} certificate={cert} />
                ))}
            </div>
          ) : (
            <CertificateEligibilityCard 
              eligibility={fullCompletionEligibility}
              userName={dashboard.user.first_name || dashboard.user.email.split("@")[0]}
            />
          )}
        </div>

        {/* Info Section */}
        <div className="mt-10 bg-gray-50 dark:bg-slate-800/30 rounded-xl p-6 border border-gray-200 dark:border-slate-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">About Certificates</h3>
          <ul className="space-y-2 text-gray-600 dark:text-slate-400 text-sm">
            <li className="flex items-start gap-2">
              <span className="text-green-500 dark:text-green-400 mt-0.5">✓</span>
              Certificates include a unique verification code
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-500 dark:text-green-400 mt-0.5">✓</span>
              Anyone can verify your certificate using the verification URL
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-500 dark:text-green-400 mt-0.5">✓</span>
              Download as PDF to share on LinkedIn or your portfolio
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-500 dark:text-green-400 mt-0.5">✓</span>
              Full program certificate requires 100% completion of all topics
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
