/**
 * Badge data for each phase.
 * Separated from PhaseCelebrationModal to satisfy React Fast Refresh rules
 * (files should only export components OR constants, not both).
 */

export const PHASE_BADGE_DATA: Record<
  number,
  { name: string; icon: string; phaseName: string }
> = {
  0: {
    name: "Cloud Seedling",
    icon: "🌱",
    phaseName: "IT Fundamentals & Cloud Overview",
  },
  1: {
    name: "Terminal Ninja",
    icon: "🐧",
    phaseName: "Command Line, Version Control & Infrastructure Basics",
  },
  2: {
    name: "Code Crafter",
    icon: "🐍",
    phaseName: "Python, FastAPI, Databases & AI Integration",
  },
  3: {
    name: "AI Apprentice",
    icon: "🤖",
    phaseName: "Prompt Engineering, GitHub Copilot & AI Tools",
  },
  4: {
    name: "Cloud Explorer",
    icon: "☁️",
    phaseName: "VMs, Networking, Security & Deployment",
  },
  5: {
    name: "DevOps Rocketeer",
    icon: "🚀",
    phaseName: "Docker, CI/CD, Kubernetes & Monitoring",
  },
  6: {
    name: "Security Guardian",
    icon: "🔐",
    phaseName: "IAM, Data Protection & Threat Detection",
  },
};
