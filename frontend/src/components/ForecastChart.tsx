import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  formatManwon,
  formatWon,
  SCENARIO_LABEL,
  type DeadPoint,
  type Scenario,
} from '../types/contract';

interface ForecastChartProps {
  /** 지금 고른 결제 방식의 시나리오. */
  scenarios: Scenario[];
  deadPoint: DeadPoint | null;
  /** 비교용으로 옅게 겹쳐 그릴 다른 방식. 없으면 안 그린다. */
  alternative?: { label: string; scenarios: Scenario[] } | null;
  /** 오늘의 가용잔고. 있으면 첫 점 앞에 '지금' 으로 붙인다. */
  startBalance?: number;
}

interface Row {
  label: string;
  mid?: number;
  low?: number;
  /** 밴드는 [하한, 상한] 쌍으로 그린다. */
  band?: [number, number];
  alt?: number;
}

/**
 * 결제 방식 하나의 6개월 잔고 추이.
 *
 * 시나리오 셋을 같은 굵기로 그리면 어느 선을 봐야 할지 알기 어렵고, 다른
 * 결제 방식과 비교할 자리도 없다. 보통(NORMAL)을 굵은 선으로 세우고 여유~빠듯을
 * 옅은 띠로 깔아 폭만 보여준다 — 예측이 점이 아니라 구간이라는 사실
 * (docs/decisions/005)을 버리지 않으면서 읽을 선은 하나로 만든다.
 *
 * 다른 방식은 회색 점선으로 겹쳐 "바꾸면 어떻게 되는지" 를 같은 그림에서
 * 보게 한다.
 *
 * 기준선은 0원이다. 시안의 "안전잔고 50만" 은 좋은 개념이지만 우리 데이터에
 * 없는 값이라 그으면 근거 없는 선이 된다. 적자 판정도 0원 기준이므로
 * (forecast/projection.py의 _find_dead_point) 선과 위기 표시가 어긋나지 않는다.
 */
export function ForecastChart({
  scenarios,
  deadPoint,
  alternative,
  startBalance,
}: ForecastChartProps) {
  const rows = toRows(scenarios, alternative?.scenarios, startBalance);

  // 굵은 선은 보통 시나리오가 0원 아래로 갈 때만 경고색이 된다.
  //
  // 빠듯 시나리오만 적자인데 굵은 선까지 빨갛게 칠하면 보통일 때도 위험한
  // 것처럼 읽힌다. 반대로 보통 시나리오가 실제로 마이너스인데 파랑으로 두면
  // 그림이 "중앙값은 안전하다" 고 말해 아래 안내 문구와 어긋난다.
  // 기준은 그 선 자신이 0원을 넘느냐 하나뿐이다(ui-system.md: 경고=빨강).
  const main = dipsBelowZero(scenarios, 'NORMAL') ? '#dc2626' : '#2563eb';
  const edge = deadPoint === null ? '#2563eb' : '#f59e0b';

  return (
    <div className="rounded-2xl bg-gray-50 p-4">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="forecast-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={main} stopOpacity={0.22} />
              <stop offset="100%" stopColor={main} stopOpacity={0.02} />
            </linearGradient>
          </defs>

          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: '#9ca3af' }}
          />
          <YAxis
            tickFormatter={formatManwon}
            tickLine={false}
            axisLine={false}
            width={44}
            tick={{ fontSize: 11, fill: '#9ca3af' }}
          />
          <Tooltip
            formatter={(value, name) => [formatWon(Number(value)), String(name)]}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
          />

          {/* 적자 기준선. 아래로 내려가면 통장이 비는 지점이다. */}
          <ReferenceLine
            y={0}
            stroke="#d1d5db"
            strokeDasharray="4 4"
            label={{ value: '잔고 0원', position: 'insideTopLeft', fontSize: 10, fill: '#9ca3af' }}
          />

          {/* 여유~빠듯 구간. 폭만 보여주고 선은 그리지 않는다. */}
          <Area
            type="monotone"
            dataKey="band"
            stroke="none"
            fill="url(#forecast-fill)"
            isAnimationActive={false}
            name="여유~빠듯"
          />

          {alternative && (
            <Line
              type="monotone"
              dataKey="alt"
              stroke="#9ca3af"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
              name={alternative.label}
            />
          )}

          {/* 빠듯 경계. 적자 판정이 이 시나리오에서 나오므로 선이 보여야
              '위기' 표시가 허공에 뜬 것처럼 읽히지 않는다. */}
          <Line
            type="monotone"
            dataKey="low"
            stroke={edge}
            strokeOpacity={deadPoint === null ? 0.4 : 0.9}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            name="빠듯"
          />

          <Line
            type="monotone"
            dataKey="mid"
            stroke={main}
            strokeWidth={3}
            dot={{ r: 3, fill: main, strokeWidth: 0 }}
            isAnimationActive={false}
            name="보통"
          />

        </ComposedChart>
      </ResponsiveContainer>

      <p className="mt-2 text-center text-[11px] text-gray-400">
        굵은 선은 {SCENARIO_LABEL.NORMAL}, 아래 얇은 선은 {SCENARIO_LABEL.TIGHT}{' '}
        시나리오입니다
        {alternative && ` · 점선은 ${alternative.label}`}
      </p>
    </div>
  );
}

/** 그 시나리오가 6개월 안에 한 번이라도 0원 아래로 내려가는지. */
function dipsBelowZero(scenarios: Scenario[], level: string): boolean {
  const points = scenarios.find((s) => s.level === level)?.points ?? [];
  return points.some((p) => p.balance < 0);
}

/**
 * 시나리오별로 나뉘어 온 응답을 한 줄로 모은다.
 * 값을 만들거나 고치지 않는다 — 백엔드가 준 balance 를 그대로 옮긴다.
 */
function toRows(
  scenarios: Scenario[],
  altScenarios?: Scenario[],
  startBalance?: number,
): Row[] {
  const pick = (list: Scenario[] | undefined, level: string) =>
    list?.find((s) => s.level === level)?.points ?? [];

  const mid = pick(scenarios, 'NORMAL');
  const high = pick(scenarios, 'COMFORTABLE');
  const low = pick(scenarios, 'TIGHT');
  const alt = pick(altScenarios, 'NORMAL');

  const rows: Row[] = mid.map((point, i) => ({
    // 절대 월(9월, 10월…)보다 상대 표기가 "지금부터 몇 달 뒤" 를 바로 읽힌다.
    label: `${i + 1}개월`,
    mid: point.balance,
    low: low[i]?.balance,
    band:
      low[i] !== undefined && high[i] !== undefined
        ? [low[i].balance, high[i].balance]
        : undefined,
    alt: alt[i]?.balance,
  }));

  // 오늘 잔고를 앞에 붙이면 "지금 이만큼인데 이렇게 된다" 가 한 줄로 읽힌다.
  if (startBalance !== undefined) {
    rows.unshift({
      label: '지금',
      mid: startBalance,
      low: startBalance,
      band: [startBalance, startBalance],
      alt: alt.length > 0 ? startBalance : undefined,
    });
  }
  return rows;
}
