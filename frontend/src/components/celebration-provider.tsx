"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { PhaseCelebrationModal, PHASE_BADGE_DATA } from "./phase-celebration-modal";

interface CelebrationContextType {
  triggerCelebration: (phaseNumber: number, nextPhaseSlug?: string) => void;
}

const CelebrationContext = createContext<CelebrationContextType | null>(null);

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

export function CelebrationProvider({ children }: { children: ReactNode }) {
  const [showCelebration, setShowCelebration] = useState(false);
  const [celebrationPhase, setCelebrationPhase] = useState<number | null>(null);
  const [nextPhaseSlug, setNextPhaseSlug] = useState<string | undefined>();

  const triggerCelebration = useCallback((phaseNumber: number, nextSlug?: string) => {
    setCelebrationPhase(phaseNumber);
    setNextPhaseSlug(nextSlug);
    setShowCelebration(true);
    markPhaseCelebrated(phaseNumber);
  }, []);

  const handleClose = useCallback(() => {
    setShowCelebration(false);
    setCelebrationPhase(null);
  }, []);

  // Expose test utilities on window
  if (typeof window !== "undefined") {
    // @ts-expect-error - Adding test utilities to window
    window.__ltcTestUtils = {
      resetCelebrations: () => {
        localStorage.removeItem(STORAGE_KEY);
        console.log("✅ Celebrations reset. Now call triggerCelebration(0) to test.");
      },
      resetPhaseCelebration: (phaseNum: number) => {
        const celebrated = getCelebratedPhases();
        celebrated.delete(phaseNum);
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...celebrated]));
        console.log(`✅ Phase ${phaseNum} celebration reset.`);
      },
      getCelebrated: () => {
        const celebrated = getCelebratedPhases();
        console.log("Celebrated phases:", [...celebrated]);
        return [...celebrated];
      },
      triggerCelebration: (phaseNum: number) => {
        const nextSlug = phaseNum < 6 ? `phase${phaseNum + 1}` : undefined;
        triggerCelebration(phaseNum, nextSlug);
        console.log(`🎉 Triggered celebration for phase ${phaseNum}`);
      },
    };
  }

  const badgeData = celebrationPhase !== null ? PHASE_BADGE_DATA[celebrationPhase] : null;

  return (
    <CelebrationContext.Provider value={{ triggerCelebration }}>
      {children}
      {badgeData && celebrationPhase !== null && (
        <PhaseCelebrationModal
          isOpen={showCelebration}
          onClose={handleClose}
          phaseNumber={celebrationPhase}
          phaseName={badgeData.phaseName}
          badgeName={badgeData.name}
          badgeIcon={badgeData.icon}
          nextPhaseSlug={nextPhaseSlug}
        />
      )}
    </CelebrationContext.Provider>
  );
}

export function useCelebration() {
  const context = useContext(CelebrationContext);
  if (!context) {
    throw new Error("useCelebration must be used within a CelebrationProvider");
  }
  return context;
}
