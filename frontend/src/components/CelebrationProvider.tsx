/**
 * Celebration Provider - provides phase completion celebrations with modal.
 * This wraps the app and manages celebration state with localStorage tracking.
 */

import { ReactNode, createContext, useContext, useCallback, useState } from 'react';
import { PhaseCelebrationModal, PHASE_BADGE_DATA } from './PhaseCelebrationModal';

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

export function useCelebration() {
  const context = useContext(CelebrationContext);
  if (!context) {
    throw new Error('useCelebration must be used within a CelebrationProvider');
  }
  return context;
}

interface CelebrationProviderProps {
  children: ReactNode;
}

export function CelebrationProvider({ children }: CelebrationProviderProps) {
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
