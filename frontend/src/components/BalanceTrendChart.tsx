import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  formatManwon,
  formatWon,
  SCENARIO_COLOR,
  SCENARIO_LABEL,
  type DeadPoint,
  type Scenario,
  type ScenarioLevel,
} from '../types/contract';

const LEVELS: ScenarioLevel[] = ['COMFORTABLE', 'NORMAL', 'TIGHT'];

interface BalanceTrendChartProps {
  scenarios: Scenario[];
  deadPoint: DeadPoint | null;
}

type ChartRow = { month: string } & Partial<Record<ScenarioLevel, number>>;

/**
 * 시나리오별로 나뉘어 온 응답을 월 기준 한 줄로 모은다.
 * 값을 만들거나 고치지 않는다 — 백엔드가 준 balance를 그대로 옮긴다.
 */
function toRows(scenarios: Scenario[]): ChartRow[] {
  const byMonth = new Map<string, ChartRow>();
  for (const scenario of scenarios) {
    for (const point of scenario.points) {
      const row = byMonth.get(point.month) ?? { month: point.month };
      row[scenario.level] = point.balance;
      byMonth.set(point.month, row);
    }
  }
  return [...byMonth.values()];
}

/** 'YYYY-MM' -> 'M월' */
function monthLabel(month: string): string {
  return `${Number(month.split('-')[1])}월`;
}

export function BalanceTrendChart({ scenarios, deadPoint }: BalanceTrendChartProps) {
  const rows = toRows(scenarios);
  const deadValue =
    deadPoint === null
      ? undefined
      : rows.find((r) => r.month === deadPoint.month)?.[deadPoint.level];

  return (
    <div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="month"
              tickFormatter={monthLabel}
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e7eb' }}
            />
            <YAxis
              tickFormatter={formatManwon}
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickLine={false}
              axisLine={false}
              width={56}
            />
            <Tooltip
              formatter={(value, name) => [
                formatWon(Number(value)),
                SCENARIO_LABEL[name as ScenarioLevel],
              ]}
              labelFormatter={(label) => monthLabel(String(label))}
              contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: '#e5e7eb' }}
            />
            {/* 적자 경계. 0원 선을 그어야 마이너스 전환이 눈에 들어온다. */}
            <ReferenceLine y={0} stroke="#dc2626" strokeDasharray="4 4" />
            {LEVELS.map((level) => (
              <Line
                key={level}
                type="monotone"
                dataKey={level}
                stroke={SCENARIO_COLOR[level]}
                // 보통(NORMAL)을 기본 강조선으로 하고 나머지는 얇게 그린다
                // (contracts/ui-system.md).
                strokeWidth={level === 'NORMAL' ? 2.5 : 1.5}
                dot={false}
                isAnimationActive={false}
              />
            ))}
            {deadPoint !== null && deadValue !== undefined && (
              <ReferenceDot
                x={deadPoint.month}
                y={deadValue}
                r={5}
                fill="#dc2626"
                stroke="#ffffff"
                strokeWidth={2}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ul className="flex gap-4 justify-center mt-2">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5 text-xs text-gray-500">
            <span
              className="inline-block w-3 h-0.5 rounded"
              style={{ backgroundColor: SCENARIO_COLOR[level] }}
            />
            {SCENARIO_LABEL[level]}
          </li>
        ))}
      </ul>
    </div>
  );
}
