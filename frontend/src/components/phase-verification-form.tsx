/**
 * Phase verification form component for Vite SPA.
 * Wraps the GitHubSubmissionForm and handles celebration on completion.
 */

import { GitHubSubmissionForm } from "./github-submission";
import { useCelebration } from "./CelebrationProvider";
import type { HandsOnRequirement, HandsOnSubmission } from "@/lib/types";

interface PhaseVerificationFormProps {
  phaseNumber: number;
  requirements: HandsOnRequirement[];
  submissions: HandsOnSubmission[];
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
