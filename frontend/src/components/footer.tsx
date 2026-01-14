import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          {/* Brand & Description */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-gray-900 dark:text-white">
                ☁️ Learn to Cloud
              </span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
              A free guide to learn the fundamentals of cloud computing
            </p>
          </div>

          {/* Links */}
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <Link
              href="/phases"
              className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              Phases
            </Link>
            <Link
              href="/faq"
              className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              FAQ
            </Link>
            <a
              href="https://github.com/learntocloud/learn-to-cloud"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              GitHub
            </a>
            <a
              href="https://discord.gg/learntocloud"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              Discord
            </a>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            © {new Date().getFullYear()} Learn to Cloud by{" "}
            <a
              href="https://x.com/madebygps"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              Gwyneth Peña-Siguenza
            </a>
            {" & "}
            <a
              href="https://x.com/rishabincloud"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              Rishab Kumar
            </a>
          </p>
          
          <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500">
            <a
              href="https://creativecommons.org/licenses/by/4.0/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              CC BY 4.0
            </a>
            <span>·</span>
            <span>Made with ❤️ for the cloud community</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
