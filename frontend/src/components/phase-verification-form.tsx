"use client";

import { GitHubSubmissionForm } from "./github-submission";
import { useCelebration } from "./celebration-provider";
import type { GitHubRequirement, Submission } from "@/lib/types";

interface PhaseVerificationFormProps {
  phaseNumber: number;
  requirements: GitHubRequirement[];
  submissions: Submission[];
  githubUsername: string | null;
  nextPhaseSlug?: string;
}

export function PhaseVerificationForm({
  phaseNumber,
  requirements,
  submissions,
  githubUsername,
  nextPhaseSlug,
}: PhaseVerificationFormProps) {
  const { triggerCelebration } = useCelebration();

  const handleAllVerificationsComplete = () => {
    triggerCelebration(phaseNumber, nextPhaseSlug);
  };

  return (
    <GitHubSubmissionForm
      requirements={requirements}
      submissions={submissions}
      githubUsername={githubUsername}
      onAllVerificationsComplete={handleAllVerificationsComplete}
    />
  );
}
