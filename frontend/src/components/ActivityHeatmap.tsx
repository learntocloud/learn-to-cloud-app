import { useMemo } from "react";
import type { ActivityHeatmapDay } from "@/lib/types";

interface ActivityHeatmapProps {
  days: ActivityHeatmapDay[];
  startDate: string;
  endDate: string;
}

const ACTIVITY_LEVELS = [0, 1, 3, 6, 10]; // 0, 1-2, 3-5, 6-9, 10+

function getActivityLevel(count: number): number {
  for (let i = ACTIVITY_LEVELS.length - 1; i >= 0; i--) {
    if (count >= ACTIVITY_LEVELS[i]) return i;
  }
  return 0;
}

const LEVEL_COLORS = [
  "bg-gray-100 dark:bg-gray-800",
  "bg-green-200 dark:bg-green-900",
  "bg-green-300 dark:bg-green-700",
  "bg-green-500 dark:bg-green-600",
  "bg-green-600 dark:bg-green-500",
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function ActivityHeatmap({ days, startDate, endDate }: ActivityHeatmapProps) {
  const activityMap = useMemo(() => {
    const map = new Map<string, ActivityHeatmapDay>();
    for (const day of days) {
      map.set(day.date, day);
    }
    return map;
  }, [days]);

  // Generate grid of weeks (columns) and days (rows)
  const grid = useMemo(() => {
    // Parse dates as UTC to avoid timezone issues
    const [startYear, startMonth, startDay] = startDate.split('-').map(Number);
    const [endYear, endMonth, endDay] = endDate.split('-').map(Number);

    const start = new Date(Date.UTC(startYear, startMonth - 1, startDay));
    const end = new Date(Date.UTC(endYear, endMonth - 1, endDay));

    if (start > end) {
      return [];
    }

    // Adjust start to the previous Sunday (in UTC)
    const adjustedStart = new Date(start);
    adjustedStart.setUTCDate(start.getUTCDate() - start.getUTCDay());

    type GridDay = { date: Date; count: number; activityTypes: string[] };
    const weeks: GridDay[][] = [];
    let currentWeek: GridDay[] = [];
    const currentDate = new Date(adjustedStart);

    while (currentDate <= end || currentWeek.length > 0) {
      const year = currentDate.getUTCFullYear();
      const month = String(currentDate.getUTCMonth() + 1).padStart(2, '0');
      const day = String(currentDate.getUTCDate()).padStart(2, '0');
      const dateStr = `${year}-${month}-${day}`;

      const isInRange = currentDate >= start && currentDate <= end;
      const dayData = activityMap.get(dateStr);

      currentWeek.push({
        date: new Date(currentDate),
        count: isInRange ? (dayData?.count || 0) : -1, // -1 for out of range
        activityTypes: isInRange ? (dayData?.activity_types || []) : [],
      });

      if (currentWeek.length === 7) {
        weeks.push(currentWeek);
        currentWeek = [];
      }

      currentDate.setUTCDate(currentDate.getUTCDate() + 1);

      if (currentDate > end && currentWeek.length === 0) {
        break;
      }
    }

    if (currentWeek.length > 0) {
      weeks.push(currentWeek);
    }

    return weeks;
  }, [startDate, endDate, activityMap]);

  const monthLabels = useMemo(() => {
    const labels: { month: string; weekIndex: number }[] = [];
    let lastMonth = -1;

    grid.forEach((week, weekIndex) => {
      const firstDayOfWeek = week[0]?.date;
      if (firstDayOfWeek) {
        const month = firstDayOfWeek.getUTCMonth();
        if (month !== lastMonth) {
          labels.push({ month: MONTHS[month], weekIndex });
          lastMonth = month;
        }
      }
    });

    return labels;
  }, [grid]);

  return (
    <div className="w-full" role="group" aria-label={`Activity heatmap from ${startDate} to ${endDate}`}>
      <div className="flex text-xs text-gray-500 dark:text-gray-400 mb-1 ml-7 justify-between pr-1">
        {monthLabels.map(({ month, weekIndex }, index) => (
          <span key={`${month}-${weekIndex}`} className={index === 0 ? "" : "flex-1 text-center"}>
            {month}
          </span>
        ))}
      </div>

      <div className="flex gap-0" role="grid" aria-readonly="true">
        <div className="flex flex-col justify-between text-xs text-gray-500 dark:text-gray-400 pr-1 py-[2px]" aria-hidden="true">
          {WEEKDAYS.map((day, i) => (
            <div key={day} className="h-2 flex items-center justify-end text-[10px]">
              {i % 2 === 1 ? day : ""}
            </div>
          ))}
        </div>

        <div className="flex-1 flex justify-between" role="rowgroup">
          {grid.map((week, weekIndex) => (
            <div key={weekIndex} className="flex flex-col gap-[2px]" role="row">
              {week.map((day, dayIndex) => {
                const level = day.count < 0 ? -1 : getActivityLevel(day.count);
                const color = level < 0 ? "bg-transparent" : LEVEL_COLORS[level];
                const hasActivity = level > 0;
                const dateStr = day.date.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  timeZone: "UTC",
                });
                const activityTypesStr = day.activityTypes.length > 0
                  ? ` (${day.activityTypes.join(", ")})`
                  : "";
                const tooltipText = `${day.count} ${day.count === 1 ? "activity" : "activities"} on ${dateStr}${activityTypesStr}`;
                const ariaLabel = level < 0 ? undefined : tooltipText;

                return (
                  <div
                    key={`${weekIndex}-${dayIndex}`}
                    className={`w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-sm ${color} ${level >= 0 ? "cursor-default" : ""} ${hasActivity ? "ring-1 ring-green-400 dark:ring-green-600" : ""}`}
                    title={level >= 0 ? tooltipText : undefined}
                    role="gridcell"
                    aria-label={ariaLabel}
                    aria-hidden={level < 0 ? "true" : undefined}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 mt-3 text-xs text-gray-500 dark:text-gray-400">
        <span>Less</span>
        {LEVEL_COLORS.map((color, i) => (
          <div
            key={i}
            className={`w-2.5 h-2.5 sm:w-3 sm:h-3 rounded-sm ${color}`}
            title={i === 0 ? "No activity" : `${ACTIVITY_LEVELS[i]}+ activities`}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}
