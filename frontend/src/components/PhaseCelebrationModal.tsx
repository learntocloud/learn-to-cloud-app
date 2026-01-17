import { useEffect, useState, useCallback, useId, useMemo, useRef } from "react";

interface PhaseCelebrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  phaseNumber: number;
  phaseName: string;
  badgeName: string;
  badgeIcon: string;
  nextPhaseSlug?: string;
}

const CONFETTI_COLORS = [
  "#FF6B6B",
  "#4ECDC4",
  "#FFE66D",
  "#95E1D3",
  "#F38181",
  "#AA96DA",
  "#FCBAD3",
  "#A8D8EA",
];

// Confetti particle component
function ConfettiParticle({
  delay,
  color,
  left,
  rotation,
}: {
  delay: number;
  color: string;
  left: number;
  rotation: number;
}) {
  return (
    <div
      className="absolute w-3 h-3 rounded-sm animate-confetti"
      style={{
        backgroundColor: color,
        left: `${left}%`,
        animationDelay: `${delay}ms`,
        transform: `rotate(${rotation}deg)`,
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
  const [confettiSeed, setConfettiSeed] = useState(0);
  const titleId = useId();
  const modalRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedElementRef = useRef<HTMLElement | null>(null);
  const previousBodyOverflowRef = useRef<string>("");

  useEffect(() => {
    if (isOpen) {
      setShowConfetti(true);
      setConfettiSeed((seed) => seed + 1);
      // Clean up confetti after animation
      const timer = setTimeout(() => setShowConfetti(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key !== "Tab") return;

      const modal = modalRef.current;
      if (!modal) return;

      const focusable = Array.from(
        modal.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((el) => !el.hasAttribute("disabled") && el.tabIndex !== -1);

      if (focusable.length === 0) {
        e.preventDefault();
        modal.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey) {
        if (!active || active === first || !modal.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (!active || active === last || !modal.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      previouslyFocusedElementRef.current = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", handleKeyDown);

      previousBodyOverflowRef.current = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      // Move focus into the dialog for a11y.
      window.setTimeout(() => {
        closeButtonRef.current?.focus();
      }, 0);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);

      document.body.style.overflow = previousBodyOverflowRef.current;

      // Restore focus to whatever triggered the dialog.
      previouslyFocusedElementRef.current?.focus?.();
    };
  }, [isOpen, handleKeyDown]);

  const confettiParticles = useMemo(() => {
    // Generate stable particle positions for a given open.
    return Array.from({ length: 50 }).map((_, i) => ({
      key: `${confettiSeed}-${i}`,
      delay: i * 50,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      left: Math.random() * 100,
      rotation: Math.random() * 360,
    }));
  }, [confettiSeed]);

  if (!isOpen) return null;

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
          {confettiParticles.map((particle) => (
            <ConfettiParticle
              key={particle.key}
              delay={particle.delay}
              color={particle.color}
              left={particle.left}
              rotation={particle.rotation}
            />
          ))}
        </div>
      )}

      {/* Modal content */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-md w-full mx-4 p-8 text-center animate-modal-pop"
      >
        {/* Badge icon - large and animated */}
        <div className="mb-6">
          <div className="inline-flex items-center justify-center w-24 h-24 text-6xl animate-bounce-slow bg-gradient-to-br from-yellow-100 to-yellow-200 dark:from-yellow-900/30 dark:to-yellow-800/30 rounded-full shadow-lg">
            {badgeIcon}
          </div>
        </div>

        {/* Celebration text */}
        <h2 id={titleId} className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
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
            ref={closeButtonRef}
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
