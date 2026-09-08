"""Static FAQ content and community/help links for pages."""

DISCUSSIONS_URL = "https://github.com/learntocloud/learn-to-cloud-app/discussions"
DISCORD_URL = "https://discord.gg/st7g2Hp77r"
GITHUB_REPOSITORY_URL = "https://github.com/learntocloud/learn-to-cloud-app"
MADEBYGPS_X_URL = "https://x.com/madebygps"
LEARN_TO_CLOUD_X_URL = "https://x.com/learntocloud"
YOUTUBE_URL = "https://youtube.com/made-by-gps"

_SPONSOR_LINK = (
    '<a href="https://github.com/sponsors/madebygps" target="_blank"'
    ' rel="noopener noreferrer"'
    ' class="text-blue-600 dark:text-blue-400 underline">sponsor us on GitHub</a>'
)
_DISCUSSIONS_LINK = (
    f'<a href="{DISCUSSIONS_URL}"'
    ' target="_blank" rel="noopener noreferrer"'
    ' class="text-blue-600 dark:text-blue-400 underline">GitHub Discussions</a>'
)

FAQS: list[tuple[str, str]] = [
    (
        "What is Learn to Cloud?",
        "Learn to Cloud is a structured, hands-on guide to learning cloud computing."
        " It takes you from the fundamentals through advanced topics with practical"
        " exercises verified by our platform.",
    ),
    (
        "Is it free?",
        f"Yes! Learn to Cloud is completely free. If you find it helpful, you can"
        f" {_SPONSOR_LINK} to support the project.",
    ),
    (
        "Do I need prior experience?",
        "No prior cloud experience is needed. Phase 0 covers prerequisites like"
        " Linux, networking, and programming fundamentals.",
    ),
    (
        "How long does it take?",
        "It depends on your pace and background. Most learners complete all phases"
        " in 3-6 months of part-time study.",
    ),
    (
        "Can I skip phases?",
        "You can read any phase, but hands-on verification builds on earlier phases."
        " We recommend following the sequence.",
    ),
    (
        "How does hands-on verification work?",
        "Each phase has practical tasks — creating a GitHub profile, deploying an"
        " API, analyzing code. You submit proof (URLs, tokens, or code) and our"
        " platform verifies it automatically.",
    ),
    (
        "What data do you collect about me?",
        "We store your GitHub ID, username, display name, avatar URL, learning"
        " progress, submissions, and feedback. We also collect operational"
        ' diagnostics. See our <a href="/privacy" class="text-blue-600'
        ' dark:text-blue-400 underline">Privacy Policy</a> for details.',
    ),
    (
        "Can I delete my account?",
        'Yes. Go to your <a href="/account" class="text-blue-600 dark:text-blue-400'
        ' underline">Account page</a> to remove your account-linked records from'
        " the active application database. Backups, diagnostics, and workflow"
        ' history have separate retention; see the <a href="/privacy"'
        ' class="text-blue-600 dark:text-blue-400 underline">Privacy Policy</a>.',
    ),
    (
        "How can I support Learn to Cloud?",
        f"You can {_SPONSOR_LINK}, share the project with others, or help fellow"
        f" learners in our {_DISCUSSIONS_LINK}.",
    ),
    (
        "Why is only GitHub login available?",
        "Our hands-on verification system relies heavily on GitHub — you submit"
        " GitHub repos, profiles, and deployments as proof of your work, and we"
        " verify them automatically. Plus, if you're serious about learning cloud,"
        " you need a GitHub account anyway. It's an essential tool for any cloud or"
        " DevOps role.",
    ),
]

_X_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true">'
    '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817'
    "L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52"
    'h1.833L7.084 4.126H5.117z"/></svg>'
)

_DISCUSSIONS_SVG = (
    '<svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none"'
    ' viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"'
    ' aria-hidden="true">'
    '<path stroke-linecap="round" stroke-linejoin="round"'
    ' d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 0 1-2-2V6'
    "a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-4l-3 3-3-3z"
    '"/></svg>'
)

_GITHUB_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 16 16" fill="currentColor"'
    ' aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54'
    " 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38"
    " 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94"
    "-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53"
    ".63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66"
    ".07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95"
    " 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12"
    " 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27"
    ".68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
    ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15"
    " 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48"
    " 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38"
    "A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
    '"/></svg>'
)

_YOUTUBE_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true"><path d="M23.498 6.186a3.016 3.016 0 0 0'
    "-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0"
    "-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12"
    " 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136"
    "c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505"
    "a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12"
    " 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818"
    ' 12l-6.273 3.568z"/></svg>'
)

_DISCORD_SVG = (
    '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor"'
    ' aria-hidden="true"><path d="M19.54 5.34A16.3 16.3 0 0 0 15.44'
    " 4l-.5 1.02a15.3 15.3 0 0 0-5.88 0L8.56 4a16.5 16.5 0 0 0"
    "-4.1 1.35C1.86 9.18 1.16 12.9 1.5 16.57A16.8 16.8 0 0 0"
    " 6.52 19.1l1.23-1.68c-.68-.25-1.33-.57-1.94-.94l.48-.37c3.74"
    " 1.73 7.8 1.73 11.5 0l.5.37c-.62.37-1.27.69-1.95.94l1.23"
    " 1.68a16.7 16.7 0 0 0 5.02-2.53c.4-4.26-.68-7.94-3.05"
    "-11.23ZM8.68 14.35c-1.12 0-2.04-1.03-2.04-2.3s.9-2.3"
    " 2.04-2.3c1.15 0 2.06 1.04 2.04 2.3 0 1.27-.9 2.3-2.04"
    " 2.3Zm6.64 0c-1.12 0-2.04-1.03-2.04-2.3s.9-2.3 2.04-2.3"
    'c1.15 0 2.06 1.04 2.04 2.3 0 1.27-.9 2.3-2.04 2.3Z"/></svg>'
)

COMMUNITY_LINKS: list[dict[str, str]] = [
    {
        "url": DISCORD_URL,
        "label": "Discord",
        "description": "Chat with other learners and get help in real time.",
        "icon": _DISCORD_SVG,
    },
    {
        "url": DISCUSSIONS_URL,
        "label": "GitHub Discussions",
        "description": "Ask questions and connect with other learners.",
        "icon": _DISCUSSIONS_SVG,
    },
    {
        "url": YOUTUBE_URL,
        "label": "YouTube",
        "description": "Watch cloud learning videos and project walkthroughs.",
        "icon": _YOUTUBE_SVG,
    },
    {
        "url": GITHUB_REPOSITORY_URL,
        "label": "GitHub",
        "description": "Explore the project, contribute, or report a problem.",
        "icon": _GITHUB_SVG,
    },
    {
        "url": MADEBYGPS_X_URL,
        "label": "Follow @madebygps",
        "description": "Follow the creator of Learn to Cloud.",
        "icon": _X_SVG,
    },
    {
        "url": LEARN_TO_CLOUD_X_URL,
        "label": "Follow @learntocloud",
        "description": "Get project news and community updates.",
        "icon": _X_SVG,
    },
]

HELP_LINKS: list[dict[str, str]] = [
    {
        "url": DISCORD_URL,
        "label": "Discord",
    },
    {
        "url": "https://github.com/learntocloud/learn-to-cloud-app/issues/new",
        "label": "Report an Issue",
    },
]
