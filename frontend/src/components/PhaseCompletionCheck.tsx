import { useEffect, useState } from "react";
import { PhaseCelebrationModal } from "./PhaseCelebrationModal";
import { PHASE_BADGE_DATA } from "./phase-badge-data";

interface PhaseCompletionCheckProps {
  phaseNumber: number;
  earnedBadges: { id: string; name: string; icon: string }[];
  nextPhaseSlug?: string;
}

const STORAGE_KEY = "ltc_celebrated_phases";

function getCelebratedPhases(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return new Set(JSON.parse(stored));
    }
  } catch {
    // Ignore localStorage errors
  }
  return new Set();
}

function markPhaseCelebrated(phaseNumber: number): void {
  if (typeof window === "undefined") return;
  try {
    const celebrated = getCelebratedPhases();
    celebrated.add(phaseNumber);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...celebrated]));
  } catch {
    // Ignore localStorage errors
  }
}

export function PhaseCompletionCheck({
  phaseNumber,
  earnedBadges,
  nextPhaseSlug,
}: PhaseCompletionCheckProps) {
  const [showCelebration, setShowCelebration] = useState(false);

  useEffect(() => {
    // Check if user has the badge for this phase
    const badgeId = `phase_${phaseNumber}_complete`;
    const hasBadge = earnedBadges.some((b) => b.id === badgeId);

    if (!hasBadge) return;

    // Check if we've already celebrated this phase
    const celebrated = getCelebratedPhases();
    if (celebrated.has(phaseNumber)) return;

    // Show celebration modal
    setShowCelebration(true);
    // Mark as celebrated so it doesn't show again
    markPhaseCelebrated(phaseNumber);
  }, [phaseNumber, earnedBadges]);

  const handleClose = () => {
    setShowCelebration(false);
  };

  const badgeData = PHASE_BADGE_DATA[phaseNumber];
  if (!badgeData) return null;

  return (
    <PhaseCelebrationModal
      isOpen={showCelebration}
      onClose={handleClose}
      phaseNumber={phaseNumber}
      phaseName={badgeData.phaseName}
      badgeName={badgeData.name}
      badgeIcon={badgeData.icon}
      nextPhaseSlug={nextPhaseSlug}
    />
  );
}
