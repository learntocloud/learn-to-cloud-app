import { useEffect, useState, useCallback } from "react";

interface PhaseCelebrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  phaseNumber: number;
  phaseName: string;
  badgeName: string;
  badgeIcon: string;
  nextPhaseSlug?: string;
}

// Confetti particle component
function ConfettiParticle({ delay, color }: { delay: number; color: string }) {
  return (
    <div
      className="absolute w-3 h-3 rounded-sm animate-confetti"
      style={{
        backgroundColor: color,
        left: `${Math.random() * 100}%`,
        animationDelay: `${delay}ms`,
        transform: `rotate(${Math.random() * 360}deg)`,
      }}
    />
  );
}

export function PhaseCelebrationModal({
  isOpen,
  onClose,
  phaseNumber,
  phaseName,
  badgeName,
  badgeIcon,
  nextPhaseSlug,
}: PhaseCelebrationModalProps) {
  const [showConfetti, setShowConfetti] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setShowConfetti(true);
      // Clean up confetti after animation
      const timer = setTimeout(() => setShowConfetti(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const confettiColors = [
    "#FF6B6B",
    "#4ECDC4",
    "#FFE66D",
    "#95E1D3",
    "#F38181",
    "#AA96DA",
    "#FCBAD3",
    "#A8D8EA",
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Confetti container */}
      {showConfetti && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {Array.from({ length: 50 }).map((_, i) => (
            <ConfettiParticle
              key={i}
              delay={i * 50}
              color={confettiColors[i % confettiColors.length]}
            />
          ))}
        </div>
      )}

      {/* Modal content */}
      <div className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-md w-full mx-4 p-8 text-center animate-modal-pop">
        {/* Badge icon - large and animated */}
        <div className="mb-6">
          <div className="inline-flex items-center justify-center w-24 h-24 text-6xl animate-bounce-slow bg-gradient-to-br from-yellow-100 to-yellow-200 dark:from-yellow-900/30 dark:to-yellow-800/30 rounded-full shadow-lg">
            {badgeIcon}
          </div>
        </div>

        {/* Celebration text */}
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          🎉 Congratulations! 🎉
        </h2>

        <p className="text-lg text-gray-600 dark:text-gray-300 mb-4">
          You&apos;ve completed
        </p>

        <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-xl p-4 mb-6">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">
            Phase {phaseNumber}
          </p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {phaseName}
          </p>
        </div>

        {/* Badge earned */}
        <div className="mb-6">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
            Badge Earned
          </p>
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-800 rounded-full">
            <span className="text-2xl">{badgeIcon}</span>
            <span className="font-semibold text-gray-900 dark:text-white">
              {badgeName}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          {nextPhaseSlug && (
            <a
              href={`/${nextPhaseSlug}`}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl transition-colors"
              onClick={onClose}
            >
              Continue to Next Phase →
            </a>
          )}
          <button
            onClick={onClose}
            className={`px-6 py-3 font-semibold rounded-xl transition-colors ${
              nextPhaseSlug
                ? "bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            {nextPhaseSlug ? "Stay Here" : "Back to Dashboard"}
          </button>
        </div>
      </div>
    </div>
  );
}
