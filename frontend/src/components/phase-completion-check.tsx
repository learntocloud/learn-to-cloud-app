"use client";

import { useEffect, useState } from "react";
import { PhaseCelebrationModal, PHASE_BADGE_DATA } from "./phase-celebration-modal";

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

// Expose test utilities on window for manual testing
if (typeof window !== "undefined") {
  // @ts-expect-error - Adding test utilities to window
  window.__ltcTestUtils = {
    // Reset all celebrations so they can be triggered again
    resetCelebrations: () => {
      localStorage.removeItem(STORAGE_KEY);
      console.log("✅ Celebrations reset. Refresh the page to see the modal again.");
    },
    // Reset a specific phase celebration
    resetPhaseCelebration: (phaseNum: number) => {
      const celebrated = getCelebratedPhases();
      celebrated.delete(phaseNum);
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...celebrated]));
      console.log(`✅ Phase ${phaseNum} celebration reset. Refresh to see it.`);
    },
    // Show which phases have been celebrated
    getCelebrated: () => {
      const celebrated = getCelebratedPhases();
      console.log("Celebrated phases:", [...celebrated]);
      return [...celebrated];
    },
    // Force trigger celebration (for testing without earning badge)
    triggerCelebration: (phaseNum: number) => {
      const event = new CustomEvent("ltc-test-celebration", { detail: { phase: phaseNum } });
      window.dispatchEvent(event);
    },
  };
  console.log("🧪 LTC Test Utils available: window.__ltcTestUtils.resetCelebrations(), .triggerCelebration(0-6)");
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

  // Listen for test trigger events
  useEffect(() => {
    const handleTestTrigger = (e: CustomEvent<{ phase: number }>) => {
      if (e.detail.phase === phaseNumber) {
        setShowCelebration(true);
      }
    };

    window.addEventListener("ltc-test-celebration" as never, handleTestTrigger as EventListener);
    return () => {
      window.removeEventListener("ltc-test-celebration" as never, handleTestTrigger as EventListener);
    };
  }, [phaseNumber]);

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
