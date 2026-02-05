import { Fragment, useMemo } from 'react';
import type { ActivityHeatmapDay } from '@/lib/types';

// ---------------------------------------------------------------------------
// Color scale (5 levels, green like GitHub)
// ---------------------------------------------------------------------------

const COLORS = {
  empty: 'bg-gray-100 dark:bg-gray-800',
  level1: 'bg-green-200 dark:bg-green-900',
  level2: 'bg-green-400 dark:bg-green-700',
  level3: 'bg-green-600 dark:bg-green-500',
  level4: 'bg-green-800 dark:bg-green-400',
} as const;

function getColorClass(count: number, max: number): string {
  if (count === 0) return COLORS.empty;
  const ratio = count / max;
  if (ratio <= 0.25) return COLORS.level1;
  if (ratio <= 0.5) return COLORS.level2;
  if (ratio <= 0.75) return COLORS.level3;
  return COLORS.level4;
}

// ---------------------------------------------------------------------------
// Month labels
// ---------------------------------------------------------------------------

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface DayCell {
  date: string; // YYYY-MM-DD
  count: number;
  dayOfWeek: number; // 0=Sun … 6=Sat
}

interface WeekColumn {
  days: (DayCell | null)[]; // length 7; null = outside range
}

function buildGrid(days: ActivityHeatmapDay[]): {
  weeks: WeekColumn[];
  maxCount: number;
  monthLabels: { label: string; colIndex: number }[];
} {
  // Build a lookup from date string → count
  const countMap = new Map<string, number>();
  let maxCount = 1;
  for (const d of days) {
    countMap.set(d.date, d.count);
    if (d.count > maxCount) maxCount = d.count;
  }

  // Generate all 365 days ending today
  const today = new Date();
  const totalDays = 365;
  const allDays: DayCell[] = [];

  for (let i = totalDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    allDays.push({
      date: dateStr,
      count: countMap.get(dateStr) ?? 0,
      dayOfWeek: d.getDay(),
    });
  }

  // Organise into week columns (columns = weeks, rows = days of week)
  const weeks: WeekColumn[] = [];
  let currentWeek: (DayCell | null)[] = new Array(7).fill(null) as (DayCell | null)[];

  // Leading empty cells for the first partial week
  const firstDow = allDays[0].dayOfWeek;
  for (let i = 0; i < firstDow; i++) {
    currentWeek[i] = null;
  }

  for (const day of allDays) {
    currentWeek[day.dayOfWeek] = day;
    if (day.dayOfWeek === 6) {
      weeks.push({ days: currentWeek });
      currentWeek = new Array(7).fill(null) as (DayCell | null)[];
    }
  }

  // Push trailing partial week
  if (currentWeek.some((d) => d !== null)) {
    weeks.push({ days: currentWeek });
  }

  // Compute month labels — place label at the first week that starts a new month
  const monthLabels: { label: string; colIndex: number }[] = [];
  let lastMonth = -1;

  for (let wIdx = 0; wIdx < weeks.length; wIdx++) {
    // Find the first non-null day in the week
    const firstDay = weeks[wIdx].days.find((d) => d !== null);
    if (!firstDay) continue;
    const month = new Date(firstDay.date).getMonth();
    if (month !== lastMonth) {
      monthLabels.push({ label: MONTH_LABELS[month], colIndex: wIdx });
      lastMonth = month;
    }
  }

  return { weeks, maxCount, monthLabels };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DAY_LABELS = ['', 'Mon', '', 'Wed', '', 'Fri', ''] as const;

interface ActivityHeatmapProps {
  days: ActivityHeatmapDay[];
}

export function ActivityHeatmap({ days }: ActivityHeatmapProps) {
  const { weeks, maxCount, monthLabels } = useMemo(() => buildGrid(days), [days]);

  const totalActivities = useMemo(
    () => days.reduce((sum, d) => sum + d.count, 0),
    [days],
  );

  return (
    <div className="bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          Activity
        </h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {totalActivities} contribution{totalActivities !== 1 ? 's' : ''} in the last year
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="inline-grid gap-0" style={{ gridTemplateColumns: `auto repeat(${weeks.length}, 1fr)` }}>
          {/* Month label row */}
          <div /> {/* spacer for day labels column */}
          {weeks.map((_, wIdx) => {
            const label = monthLabels.find((m) => m.colIndex === wIdx);
            return (
              <div key={`m-${wIdx}`} className="text-[10px] text-gray-400 dark:text-gray-500 h-4 leading-4 px-px">
                {label?.label ?? ''}
              </div>
            );
          })}

          {/* Day rows */}
          {Array.from({ length: 7 }).map((_, rowIdx) => (
            <Fragment key={`row-${rowIdx}`}>
              {/* Day label */}
              <div
                className="text-[10px] text-gray-400 dark:text-gray-500 pr-1 h-3.25 leading-3.25 text-right"
              >
                {DAY_LABELS[rowIdx]}
              </div>

              {/* Cells */}
              {weeks.map((week, wIdx) => {
                const cell = week.days[rowIdx];
                if (!cell) {
                  return <div key={`c-${wIdx}-${rowIdx}`} className="w-2.75 h-2.75 m-px" />;
                }
                const colorClass = getColorClass(cell.count, maxCount);
                return (
                  <div
                    key={`c-${wIdx}-${rowIdx}`}
                    className={`w-2.75 h-2.75 m-px rounded-sm ${colorClass}`}
                    title={`${cell.date}: ${cell.count} activit${cell.count === 1 ? 'y' : 'ies'}`}
                    role="img"
                    aria-label={`${cell.date}: ${cell.count} activit${cell.count === 1 ? 'y' : 'ies'}`}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-end gap-1 mt-2">
        <span className="text-[10px] text-gray-400 dark:text-gray-500 mr-1">Less</span>
        <div className={`w-2.75 h-2.75 rounded-sm ${COLORS.empty}`} />
        <div className={`w-2.75 h-2.75 rounded-sm ${COLORS.level1}`} />
        <div className={`w-2.75 h-2.75 rounded-sm ${COLORS.level2}`} />
        <div className={`w-2.75 h-2.75 rounded-sm ${COLORS.level3}`} />
        <div className={`w-2.75 h-2.75 rounded-sm ${COLORS.level4}`} />
        <span className="text-[10px] text-gray-400 dark:text-gray-500 ml-1">More</span>
      </div>
    </div>
  );
}
