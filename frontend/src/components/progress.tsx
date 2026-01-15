import type { CompletionStatus } from "@/lib/types";

interface ProgressBarProps {
  percentage: number;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  status?: CompletionStatus;  // Optional status to determine color
}

export function ProgressBar({ percentage, size = "md", showLabel = true, status }: ProgressBarProps) {
  const heights = {
    sm: "h-1.5",
    md: "h-2.5",
    lg: "h-4",
  };

  const getColor = (pct: number, completionStatus?: CompletionStatus) => {
    // If status is provided, use it for coloring
    if (completionStatus === 'completed') return "bg-green-500";
    if (completionStatus === 'in_progress') return "bg-blue-500";
    if (completionStatus === 'not_started') return "bg-gray-300 dark:bg-gray-600";

    // Fallback to percentage-based coloring
    if (pct === 100) return "bg-green-500";
    if (pct > 50) return "bg-blue-500";
    if (pct > 0) return "bg-yellow-500";
    return "bg-gray-300 dark:bg-gray-600";
  };

  return (
    <div className="w-full">
      <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full ${heights[size]} overflow-hidden`}>
        <div
          className={`${getColor(percentage, status)} ${heights[size]} rounded-full transition-all duration-500 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{Math.round(percentage)}% complete</p>
      )}
    </div>
  );
}

interface StatusBadgeProps {
  status: CompletionStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const styles = {
    not_started: "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300",
    in_progress: "bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200",
    completed: "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200",
  };

  const labels = {
    not_started: "Not Started",
    in_progress: "In Progress",
    completed: "Completed",
  };

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}
