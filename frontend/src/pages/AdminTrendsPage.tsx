import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import { useTrends, useAggregateToday, useAggregateYesterday, useDashboard } from '@/lib/hooks';
import type { DailyMetricsData } from '@/lib/types';

export function AdminTrendsPage() {
  const { isSignedIn, isLoaded } = useUser();
  const { data: dashboard, isLoading: dashboardLoading } = useDashboard();

  if (!isLoaded || dashboardLoading) {
    return (
      <div className="py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate to="/" replace />;
  }

  if (dashboard && !dashboard.user.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="py-8 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950 min-h-screen">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <AdminTrendsContent />
      </div>
    </div>
  );
}

function AdminTrendsContent() {
  const [days, setDays] = useState(30);
  const { data: trends, isLoading, error, refetch } = useTrends(days);
  const aggregateToday = useAggregateToday();
  const aggregateYesterday = useAggregateYesterday();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !trends) {
    return (
      <div className="text-center py-20">
        <p className="text-red-500 mb-4">
          {error instanceof Error ? error.message : 'Failed to load trends'}
        </p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  const { summary } = trends;

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Analytics Dashboard
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {trends.start_date} to {trends.end_date}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>

          <button
            onClick={() => aggregateYesterday.mutate()}
            disabled={aggregateYesterday.isPending}
            className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg disabled:opacity-50"
          >
            {aggregateYesterday.isPending ? 'Running...' : 'Aggregate Yesterday'}
          </button>

          <button
            onClick={() => aggregateToday.mutate()}
            disabled={aggregateToday.isPending}
            className="px-3 py-2 text-sm bg-blue-600 text-white hover:bg-blue-700 rounded-lg disabled:opacity-50"
          >
            {aggregateToday.isPending ? 'Running...' : 'Aggregate Today'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <SummaryCard
          label="Total Users"
          value={summary.cumulative_users.toLocaleString()}
          subValue={`+${summary.total_new_signups} this period`}
        />
        <SummaryCard
          label="Avg Daily Active"
          value={summary.avg_daily_active_users.toFixed(1)}
          subValue={
            summary.active_users_wow_change >= 0
              ? `+${summary.active_users_wow_change}% WoW`
              : `${summary.active_users_wow_change}% WoW`
          }
          trend={summary.active_users_wow_change >= 0 ? 'up' : 'down'}
        />
        <SummaryCard
          label="Pass Rate"
          value={`${summary.overall_pass_rate}%`}
          subValue={`${summary.total_questions_passed}/${summary.total_questions_attempted} questions`}
        />
        <SummaryCard
          label="Certificates"
          value={summary.cumulative_certificates.toLocaleString()}
          subValue={`+${summary.total_certificates_earned} this period`}
        />
      </div>

      {/* Activity Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <MetricCard label="Steps Completed" value={summary.total_steps_completed} />
        <MetricCard label="Questions Attempted" value={summary.total_questions_attempted} />
        <MetricCard label="Questions Passed" value={summary.total_questions_passed} />
        <MetricCard label="Phases Completed" value={summary.total_phases_completed} />
        <MetricCard label="Hands-On Validated" value={trends.days.reduce((sum, d) => sum + d.hands_on_validated, 0)} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <ChartCard title="Daily Active Users">
          <SimpleLineChart
            data={trends.days}
            dataKey="active_users"
            color="#3b82f6"
          />
        </ChartCard>

        <ChartCard title="New Signups">
          <SimpleLineChart
            data={trends.days}
            dataKey="new_signups"
            color="#10b981"
          />
        </ChartCard>

        <ChartCard title="Questions Pass Rate (%)">
          <SimpleLineChart
            data={trends.days}
            dataKey="question_pass_rate"
            color="#f59e0b"
          />
        </ChartCard>

        <ChartCard title="Learning Activity">
          <SimpleLineChart
            data={trends.days}
            dataKey="steps_completed"
            color="#8b5cf6"
          />
        </ChartCard>
      </div>

      {/* Data Table */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <h2 className="font-semibold text-gray-900 dark:text-white">Daily Breakdown</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-700/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-300">Date</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Active</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">New</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Steps</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Questions</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Pass %</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Phases</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-300">Certs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {trends.days.map((day) => (
                <tr key={day.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-4 py-3 text-gray-900 dark:text-white font-medium">{day.date}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.active_users}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.new_signups}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.steps_completed}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">
                    {day.questions_passed}/{day.questions_attempted}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.question_pass_rate}%</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.phases_completed}</td>
                  <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 tabular-nums">{day.certificates_earned}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function SummaryCard({
  label,
  value,
  subValue,
  trend,
}: {
  label: string;
  value: string;
  subValue: string;
  trend?: 'up' | 'down';
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{value}</p>
      <p className={`text-xs mt-1 ${
        trend === 'up' ? 'text-green-600 dark:text-green-400' :
        trend === 'down' ? 'text-red-600 dark:text-red-400' :
        'text-gray-500 dark:text-gray-400'
      }`}>
        {subValue}
      </p>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-lg font-semibold text-gray-900 dark:text-white tabular-nums">
        {value.toLocaleString()}
      </p>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">{title}</h3>
      {children}
    </div>
  );
}

function SimpleLineChart({
  data,
  dataKey,
  color,
}: {
  data: DailyMetricsData[];
  dataKey: keyof DailyMetricsData;
  color: string;
}) {
  // Reverse to show oldest first (left to right)
  const chartData = [...data].reverse();

  if (chartData.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-gray-400">
        No data
      </div>
    );
  }

  const values = chartData.map((d) => Number(d[dataKey]));
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  const width = 100;
  const height = 40;
  const padding = 2;

  const points = chartData.map((d, i) => {
    const x = padding + (i / (chartData.length - 1 || 1)) * (width - 2 * padding);
    const y = height - padding - ((Number(d[dataKey]) - min) / range) * (height - 2 * padding);
    return `${x},${y}`;
  }).join(' ');

  // Create area path (line + fill below)
  const areaPath = chartData.map((d, i) => {
    const x = padding + (i / (chartData.length - 1 || 1)) * (width - 2 * padding);
    const y = height - padding - ((Number(d[dataKey]) - min) / range) * (height - 2 * padding);
    return i === 0 ? `M ${x},${y}` : `L ${x},${y}`;
  }).join(' ') + ` L ${width - padding},${height - padding} L ${padding},${height - padding} Z`;

  return (
    <div className="h-40">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-32"
        preserveAspectRatio="none"
      >
        {/* Area fill */}
        <path
          d={areaPath}
          fill={color}
          fillOpacity={0.1}
        />
        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={0.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="flex justify-between text-xs text-gray-400 mt-2">
        <span>{chartData[0]?.date.slice(5)}</span>
        <span className="font-medium" style={{ color }}>
          Latest: {values[values.length - 1]?.toLocaleString()}
        </span>
        <span>{chartData[chartData.length - 1]?.date.slice(5)}</span>
      </div>
    </div>
  );
}
