"use client";

import { useMemo } from "react";
import type { ActivityHeatmapDay } from "@/lib/types";

interface ActivityHeatmapProps {
  days: ActivityHeatmapDay[];
  startDate: string;
  endDate: string;
}

// Activity level thresholds
const ACTIVITY_LEVELS = [0, 1, 3, 6, 10]; // 0, 1-2, 3-5, 6-9, 10+

function getActivityLevel(count: number): number {
  for (let i = ACTIVITY_LEVELS.length - 1; i >= 0; i--) {
    if (count >= ACTIVITY_LEVELS[i]) return i;
  }
  return 0;
}

const LEVEL_COLORS = [
  "bg-gray-100 dark:bg-gray-800", // Level 0 - no activity
  "bg-green-200 dark:bg-green-900", // Level 1
  "bg-green-300 dark:bg-green-700", // Level 2
  "bg-green-500 dark:bg-green-600", // Level 3
  "bg-green-600 dark:bg-green-500", // Level 4
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function ActivityHeatmap({ days, startDate, endDate }: ActivityHeatmapProps) {
  // Build a map of date -> count for quick lookup
  const activityMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const day of days) {
      map.set(day.date, day.count);
    }
    return map;
  }, [days]);

  // Generate grid of weeks (columns) and days (rows)
  const grid = useMemo(() => {
    const start = new Date(startDate);
    const end = new Date(endDate);
    
    // Adjust start to the previous Sunday
    const adjustedStart = new Date(start);
    adjustedStart.setDate(start.getDate() - start.getDay());
    
    const weeks: { date: Date; count: number }[][] = [];
    let currentWeek: { date: Date; count: number }[] = [];
    let currentDate = new Date(adjustedStart);
    
    while (currentDate <= end || currentWeek.length > 0) {
      const dateStr = currentDate.toISOString().split("T")[0];
      const isInRange = currentDate >= start && currentDate <= end;
      
      currentWeek.push({
        date: new Date(currentDate),
        count: isInRange ? (activityMap.get(dateStr) || 0) : -1, // -1 for out of range
      });
      
      if (currentWeek.length === 7) {
        weeks.push(currentWeek);
        currentWeek = [];
      }
      
      currentDate.setDate(currentDate.getDate() + 1);
      
      // Break if we've gone past end date and completed the week
      if (currentDate > end && currentWeek.length === 0) {
        break;
      }
    }
    
    // Add any remaining partial week
    if (currentWeek.length > 0) {
      weeks.push(currentWeek);
    }
    
    return weeks;
  }, [startDate, endDate, activityMap]);

  // Get month labels
  const monthLabels = useMemo(() => {
    const labels: { month: string; weekIndex: number }[] = [];
    let lastMonth = -1;
    
    grid.forEach((week, weekIndex) => {
      const firstDayOfWeek = week[0]?.date;
      if (firstDayOfWeek) {
        const month = firstDayOfWeek.getMonth();
        if (month !== lastMonth) {
          labels.push({ month: MONTHS[month], weekIndex });
          lastMonth = month;
        }
      }
    });
    
    return labels;
  }, [grid]);

  return (
    <div className="overflow-x-auto">
      {/* Month labels */}
      <div className="flex text-xs text-gray-500 dark:text-gray-400 mb-1 pl-8">
        {monthLabels.map(({ month, weekIndex }) => (
          <span
            key={`${month}-${weekIndex}`}
            className="absolute"
            style={{ marginLeft: `${weekIndex * 14}px` }}
          >
            {month}
          </span>
        ))}
      </div>
      
      <div className="flex gap-[2px] relative mt-4">
        {/* Weekday labels */}
        <div className="flex flex-col gap-[2px] text-xs text-gray-500 dark:text-gray-400 pr-1">
          {WEEKDAYS.map((day, i) => (
            <div key={day} className="h-3 w-6 flex items-center justify-end text-[10px]">
              {i % 2 === 1 ? day : ""}
            </div>
          ))}
        </div>
        
        {/* Activity grid */}
        <div className="flex gap-[2px]">
          {grid.map((week, weekIndex) => (
            <div key={weekIndex} className="flex flex-col gap-[2px]">
              {week.map((day, dayIndex) => {
                const level = day.count < 0 ? -1 : getActivityLevel(day.count);
                const color = level < 0 ? "bg-transparent" : LEVEL_COLORS[level];
                const dateStr = day.date.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                });
                
                return (
                  <div
                    key={`${weekIndex}-${dayIndex}`}
                    className={`w-3 h-3 rounded-sm ${color} ${level >= 0 ? "cursor-default" : ""}`}
                    title={level >= 0 ? `${day.count} activities on ${dateStr}` : undefined}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
      
      {/* Legend */}
      <div className="flex items-center gap-2 mt-4 text-xs text-gray-500 dark:text-gray-400">
        <span>Less</span>
        {LEVEL_COLORS.map((color, i) => (
          <div
            key={i}
            className={`w-3 h-3 rounded-sm ${color}`}
            title={i === 0 ? "No activity" : `${ACTIVITY_LEVELS[i]}+ activities`}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}
