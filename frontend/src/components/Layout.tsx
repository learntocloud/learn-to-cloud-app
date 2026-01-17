import { Link, useNavigate, useLocation } from 'react-router-dom';
import { UserButton, SignInButton, useUser } from '@clerk/clerk-react';
import { useEffect, useRef } from 'react';
import { useUserInfo } from '@/lib/hooks';
import { ThemeToggle } from './ThemeToggle';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-950">
      {/* Skip to main content link for keyboard navigation accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:shadow-lg"
      >
        Skip to main content
      </a>
      <Navbar />
      <main id="main-content" className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

function Navbar() {
  const { isSignedIn, isLoaded } = useUser();
  const { data: userInfo } = useUserInfo();
  const navigate = useNavigate();
  const location = useLocation();
  const wasSignedIn = useRef<boolean | null>(null);

  // Redirect to dashboard when user signs in (e.g., via modal)
  useEffect(() => {
    if (!isLoaded) {
      return;
    }

    // Initialize once after auth state is loaded so we don't treat the initial
    // hydration on page refresh as a "sign-in" event.
    if (wasSignedIn.current === null) {
      wasSignedIn.current = isSignedIn;
      return;
    }

    if (isSignedIn && !wasSignedIn.current) {
      // User just signed in - redirect to dashboard if on a public page
      const publicPages = ['/', '/faq', '/phases', '/sign-in', '/sign-up'];
      const isOnPublicPage = publicPages.some(page => location.pathname === page || location.pathname.startsWith('/sign-'));
      if (isOnPublicPage) {
        navigate('/dashboard');
      }
    }
    wasSignedIn.current = isSignedIn;
  }, [isSignedIn, isLoaded, navigate, location.pathname]);


  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link to="/" className="flex items-center">
              <svg className="h-8 w-auto text-blue-600 dark:text-blue-400" viewBox="200 320 600 370" fill="currentColor">
                <path d="M600.5,387.3c-4.9,0-9.7,0.5-14.5,1.6c-12.8-35.2-46.8-59.4-84.8-59.4c-37.9,0-71.9,24.1-84.7,59.4c-6.1-1.3-12.4-1.8-18.7-1.4c-35.4,2.2-63.1,32.2-62.6,67.6c0.5,36.5,30.3,66.1,66.9,66.1h5.8v0h12v0h14.9c15,0,27.2-12.2,27.2-27.2v-12.1c4.9-3.2,8-9.1,7.1-15.5c-1-7.1-6.8-12.8-13.9-13.6c-9.6-1.1-17.7,6.4-17.7,15.8c0,7.6,5.4,14,12.6,15.5v9.9c0,8.4-6.8,15.2-15.2,15.2h-14.9v0h-12v0H402c-0.5,0-1.1,0-1.6,0h-3.6v-0.2c-27.4-2.6-49-25.4-49.7-53.2c-0.8-29.3,22-54.4,51.3-56.3c6.9-0.4,13.7,0.4,20.2,2.4l0,0c3.2,1,6.6-0.8,7.6-4l0,0c9.6-33.2,40.5-56.3,75-56.3c34.6,0,65.4,23.2,75.1,56.3l0,0c0.9,3.2,4.4,5.1,7.6,4l0,0c6.5-2.1,13.4-2.9,20.2-2.4c28.9,1.9,51.6,26.4,51.3,55.3c-0.2,27.1-20.3,49.6-46.4,53.7v0.6h-7.1c-0.5,0-1,0-1.5,0h-5.8v0h-12v0h-15.9c-8.4,0-15.2-6.8-15.2-15.2v-10c7.1-1.8,12.4-8.3,12.1-16.1c-0.3-8.1-7-14.8-15.1-15.2c-9.1-0.4-16.7,6.9-16.7,15.9c0,5.8,3.1,10.8,7.7,13.6v11.8c0,15,12.2,27.2,27.2,27.2h15.9v0h12v0h4.8c36.7,0,67.4-29.2,67.9-65.9C668,417.9,637.7,387.3,600.5,387.3z M449.4,468.5c0-2.2,1.7-3.9,3.9-3.9s3.9,1.7,3.9,3.9s-1.7,3.9-3.9,3.9S449.4,470.7,449.4,468.5z M547.8,472.4c-2.2,0-3.9-1.7-3.9-3.9s1.7-3.9,3.9-3.9c2.2,0,3.9,1.7,3.9,3.9S549.9,472.4,547.8,472.4z"/>
                <path d="M588.7,501.1c3.3,0,6-2.7,6-6l0-70c0-3.2-1.1-6.4-3.3-8.8c-3.7-4-9.3-5.2-14.1-3.3L520,437.5c-2.3,0.9-3.8,3.1-3.8,5.6v0c0,4.2,4.3,7.1,8.2,5.6l57.3-24.4c0.1,0,0.3-0.1,0.6,0.1c0.3,0.2,0.3,0.5,0.3,0.6v70.2C582.7,498.4,585.4,501.1,588.7,501.1z"/>
                <path d="M487.3,443.1c0-2.5-1.5-4.7-3.8-5.6l-58.2-24.4c-4.8-1.9-10.4-0.7-14.1,3.3c-2.2,2.4-3.3,5.6-3.3,8.8v71c0,3.3,2.7,6,6,6s6-2.7,6-6v-71.2c0-0.1,0-0.4,0.3-0.6c0.1-0.1,0.3-0.1,0.4-0.1c0.1,0,0.2,0,0.3,0.1l58.2,24.4C483,450.2,487.3,447.3,487.3,443.1z"/>
                <path d="M588.7,528.2c-3.3,0-6,2.7-6,6v9.9c0,0.3-0.2,0.6-0.5,0.7l-74.9,23.1V466h0v-12.4v-12.9v-15.5h0v-34.9c5.9-2.4,10.1-8.3,9.9-15.2c-0.2-8.2-6.9-15-15.1-15.4c-9.1-0.4-16.7,6.9-16.7,15.9c0,6.6,4.1,12.3,9.9,14.7v32.7h0v17.7v12.9v10.2h0v104.1l-74.9-23.1c-0.3-0.1-0.5-0.4-0.5-0.7v-8.9c0-3.3-2.7-6-6-6s-6,2.7-6,6v8.9c0,5.6,3.6,10.5,8.9,12.1l84.4,26.1l84.4-26.1c5.4-1.7,9-6.5,9-12.1v-9.9C594.7,530.9,592,528.2,588.7,528.2z M501.3,379.6c-2.2,0-3.9-1.7-3.9-3.9s1.7-3.9,3.9-3.9c2.2,0,3.9,1.7,3.9,3.9S503.4,379.6,501.3,379.6z"/>
              </svg>
            </Link>
            <div className="hidden sm:ml-8 sm:flex sm:space-x-4">
              <Link to="/faq" className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-2 text-sm font-medium">
                FAQ
              </Link>
              {isSignedIn && (
                <>
                  <Link to="/dashboard" className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-2 text-sm font-medium">
                    Dashboard
                  </Link>
                  {userInfo?.github_username && (
                    <Link to={`/user/${userInfo.github_username}`} className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-2 text-sm font-medium">
                      Profile
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden sm:flex items-center gap-1 mr-2">
              <a href="https://discord.learntocloud.guide" target="_blank" rel="noopener noreferrer" className="p-2 text-gray-500 hover:text-indigo-500 dark:text-gray-400 dark:hover:text-indigo-400 transition-colors" aria-label="Join our Discord">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>
              </a>
              <a href="https://github.com/learntocloud/learn-to-cloud-app" target="_blank" rel="noopener noreferrer" className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors" aria-label="GitHub">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              </a>
              <a href="https://x.com/madebygps" target="_blank" rel="noopener noreferrer" className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors" aria-label="Follow on X">
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              </a>
            </div>
            <ThemeToggle />
            {isLoaded && (
              <>
                {isSignedIn ? (
                  <UserButton />
                ) : (
                  <SignInButton mode="modal">
                    <button className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
                      Sign In
                    </button>
                  </SignInButton>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}

function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-gray-900 dark:text-white">☁️ Learn to Cloud</span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
              A free guide to learn the fundamentals of cloud computing
            </p>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <Link to="/phases" className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">Phases</Link>
            <Link to="/faq" className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">FAQ</Link>
            <a href="https://github.com/learntocloud/learn-to-cloud-app" target="_blank" rel="noopener noreferrer" className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">GitHub</a>
            <a href="https://discord.learntocloud.guide" target="_blank" rel="noopener noreferrer" className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">Discord</a>
          </div>
        </div>
        <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            © {new Date().getFullYear()} Learn to Cloud by{' '}
            <a href="https://x.com/madebygps" target="_blank" rel="noopener noreferrer" className="hover:text-gray-600 dark:hover:text-gray-300">Gwyneth Peña-Siguenza</a>
            {' & '}
            <a href="https://x.com/rishabincloud" target="_blank" rel="noopener noreferrer" className="hover:text-gray-600 dark:hover:text-gray-300">Rishab Kumar</a>
          </p>
          <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500">
            <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer" className="hover:text-gray-600 dark:hover:text-gray-300">CC BY 4.0</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
