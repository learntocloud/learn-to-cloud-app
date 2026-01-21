import { useEffect, useState, useCallback } from "react";
import { PhaseCelebrationModal } from "./PhaseCelebrationModal";
import { PHASE_BADGES } from "@/lib/constants";

interface PhaseCompletionCheckProps {
  phaseNumber: number;
  earnedBadges: Array<{ id: string }>;
  nextPhaseSlug?: string;
}

const STORAGE_KEY = "ltc_celebrated_phases";

function getCelebratedPhases(): Set<number> {
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
  const badgeData = PHASE_BADGES[phaseNumber];
  const [showCelebration, setShowCelebration] = useState(false);

  useEffect(() => {
    if (!badgeData) return;

    const badgeId = `phase_${phaseNumber}_complete`;
    const hasBadge = earnedBadges.some((b) => b.id === badgeId);
    if (!hasBadge) return;

    const celebrated = getCelebratedPhases();
    if (celebrated.has(phaseNumber)) return;

    // Mark as celebrated only when modal closes, not here
    setShowCelebration(true);
  }, [phaseNumber, earnedBadges, badgeData]);

  const handleClose = useCallback(() => {
    markPhaseCelebrated(phaseNumber);
    setShowCelebration(false);
  }, [phaseNumber]);

  if (!badgeData || !showCelebration) return null;

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
