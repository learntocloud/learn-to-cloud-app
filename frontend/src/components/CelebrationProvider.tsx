/**
 * Celebration Provider - provides confetti and celebration animations.
 * This wraps the app and listens for celebration events.
 */

import { ReactNode, createContext, useContext, useCallback, useState } from 'react';

interface CelebrationContextType {
  celebrate: () => void;
}

const CelebrationContext = createContext<CelebrationContextType | null>(null);

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
  const [showConfetti, setShowConfetti] = useState(false);

  const celebrate = useCallback(() => {
    setShowConfetti(true);
    setTimeout(() => setShowConfetti(false), 3000);
  }, []);

  return (
    <CelebrationContext.Provider value={{ celebrate }}>
      {children}
      {showConfetti && (
        <div className="fixed inset-0 pointer-events-none z-50">
          {/* Simple confetti animation */}
          <div className="absolute inset-0 overflow-hidden">
            {Array.from({ length: 50 }).map((_, i) => (
              <div
                key={i}
                className="absolute animate-confetti"
                style={{
                  left: `${Math.random() * 100}%`,
                  top: '-10%',
                  width: '10px',
                  height: '10px',
                  backgroundColor: ['#ff0', '#f0f', '#0ff', '#f00', '#0f0', '#00f'][Math.floor(Math.random() * 6)],
                  borderRadius: Math.random() > 0.5 ? '50%' : '0',
                  animationDelay: `${Math.random() * 2}s`,
                  animationDuration: `${2 + Math.random() * 2}s`,
                }}
              />
            ))}
          </div>
        </div>
      )}
    </CelebrationContext.Provider>
  );
}
