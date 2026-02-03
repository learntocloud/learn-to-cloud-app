import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { UpdatesResponse, UpdatesCommit } from '@/lib/types';
import { createApiClient } from '@/lib/api-client';

export function UpdatesPage() {
  const [data, setData] = useState<UpdatesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const api = useMemo(() => createApiClient(async () => null), []);

  useEffect(() => {
    document.title = 'Updates - Learn to Cloud';
    fetchUpdates();
  }, []);

  async function fetchUpdates() {
    try {
      setLoading(true);
      const result = await api.getUpdates();
      setData(result);
      setError(result.error || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load updates');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen py-12 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <header className="mb-12">
          <Link
            to="/"
            className="text-gray-400 dark:text-gray-500 hover:text-indigo-500 dark:hover:text-indigo-400 text-sm transition-colors"
          >
            ← learntocloud.guide
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
            Updates
          </h1>
          {data && (
            <p className="mt-2 text-gray-600 dark:text-gray-300">
              {data.week_display}
            </p>
          )}
        </header>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : error ? (
          <div className="text-center py-20">
            <p className="text-red-500 dark:text-red-400 mb-4">{error}</p>
            <button
              onClick={fetchUpdates}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : !data || data.commits.length === 0 ? (
          <p className="text-center text-gray-500 dark:text-gray-400 py-20">
            No updates this week yet. Check back soon!
          </p>
        ) : (
          <ul className="space-y-1">
            {data.commits.map((commit: UpdatesCommit) => (
              <li
                key={commit.sha}
                className="flex items-start gap-3 py-2 border-b border-gray-100 dark:border-gray-800 last:border-0"
              >
                <span className="text-base flex-shrink-0 mt-0.5" aria-hidden="true">
                  {commit.emoji}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-gray-900 dark:text-white text-sm leading-relaxed">
                    {commit.message}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    <a
                      href={commit.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-indigo-500 dark:text-indigo-400 hover:underline"
                    >
                      {commit.sha}
                    </a>
                    <span className="ml-2">by {commit.author}</span>
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Footer */}
        {data && (
          <footer className="mt-16 pt-8 border-t border-gray-200 dark:border-gray-800 text-center text-sm text-gray-400 dark:text-gray-500">
            <p>
              Generated from commits to{' '}
              <a
                href={`https://github.com/${data.repo.owner}/${data.repo.name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-500 dark:text-indigo-400 hover:underline"
              >
                {data.repo.owner}/{data.repo.name}
              </a>
            </p>
          </footer>
        )}
      </div>
    </main>
  );
}
