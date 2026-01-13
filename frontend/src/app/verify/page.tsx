import Link from "next/link";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

interface VerifyIndexPageProps {
  searchParams?: { code?: string | string[] } | Promise<{ code?: string | string[] }>;
}

export default async function VerifyIndexPage({ searchParams }: VerifyIndexPageProps) {
  const resolved = await Promise.resolve(searchParams);
  const raw = resolved?.code;
  const code = (Array.isArray(raw) ? raw[0] : raw)?.trim();

  if (code) {
    redirect(`/verify/${encodeURIComponent(code)}`);
  }

  return (
    <div className="min-h-screen py-10">
      <div className="max-w-xl mx-auto px-4 sm:px-6">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white text-sm mb-6 transition-colors group"
        >
          <svg
            className="w-4 h-4 transition-transform group-hover:-translate-x-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Learn to Cloud
        </Link>

        <div className="rounded-2xl bg-white dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700/50 p-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Verify a Certificate</h1>
          <p className="mt-2 text-gray-600 dark:text-slate-300">
            Paste a verification code from a Learn to Cloud certificate.
          </p>

          <form action="/verify" method="GET" className="mt-6 space-y-3">
            <label className="block">
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Verification code</span>
              <input
                name="code"
                placeholder="LTC-XXXX..."
                className="mt-2 w-full rounded-xl border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-900/40 px-4 py-3 text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/60"
                autoComplete="off"
                spellCheck={false}
              />
            </label>

            <button
              type="submit"
              className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-amber-500 hover:bg-amber-600 text-gray-950 font-semibold transition-colors"
            >
              Verify
            </button>
          </form>

          <p className="mt-4 text-xs text-gray-500 dark:text-slate-500">
            Tip: If you already have a link like /verify/&lt;code&gt;, just open it directly.
          </p>
        </div>
      </div>
    </div>
  );
}
