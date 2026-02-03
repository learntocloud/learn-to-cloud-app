import { useEffect, useState, useCallback } from "react";
import { PhaseCelebrationModal } from "./PhaseCelebrationModal";
import type { BadgeCatalogItem } from "@/lib/types";

interface PhaseCompletionCheckProps {
  phaseNumber: number;
  earnedBadges: Array<{ id: string }>;
  nextPhaseSlug?: string;
  phaseBadge?: BadgeCatalogItem | null;
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
  phaseBadge,
}: PhaseCompletionCheckProps) {
  const [showCelebration, setShowCelebration] = useState(false);

  useEffect(() => {
    if (!phaseBadge) return;

    const hasBadge = earnedBadges.some((b) => b.id === phaseBadge.id);
    if (!hasBadge) return;

    const celebrated = getCelebratedPhases();
    if (celebrated.has(phaseNumber)) return;

    // Mark as celebrated only when modal closes, not here
    setShowCelebration(true);
  }, [phaseNumber, earnedBadges, phaseBadge]);

  const handleClose = useCallback(() => {
    markPhaseCelebrated(phaseNumber);
    setShowCelebration(false);
  }, [phaseNumber]);

  if (!phaseBadge || !showCelebration) return null;

  return (
    <PhaseCelebrationModal
      isOpen={showCelebration}
      onClose={handleClose}
      phaseNumber={phaseNumber}
      phaseName={phaseBadge.phase_name || `Phase ${phaseNumber}`}
      badgeName={phaseBadge.name}
      badgeIcon={phaseBadge.icon}
      nextPhaseSlug={nextPhaseSlug}
    />
  );
}
