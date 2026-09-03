import {
  Area,
  ComposedChart,
  Line,
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
  SCENARIO_LABEL,
  type DeadPoint,
  type Scenario,
} from '../types/contract';

const CHART_HEIGHT = 240;
/** recharts XAxis 기본 높이. 이 아래는 눈금 글자 자리다. */
const X_AXIS_HEIGHT = 30;
const PLOT_BOTTOM = CHART_HEIGHT - X_AXIS_HEIGHT;
/** 위기 말풍선을 점에서 얼마나 띄울지, 그리고 그 절반 높이. */
const PILL_OFFSET = 20;
const PILL_HALF = 9;

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
  const midDips = dipsBelowZero(scenarios, 'NORMAL');
  const main = midDips ? '#dc2626' : '#2563eb';
  const edge = deadPoint === null ? '#2563eb' : '#f59e0b';

  // 위기 표시 색은 아래 안내 상자와 같은 기준(보통 시나리오가 적자인가)을
  // 쓴다.
  //
  // 점이 놓인 선의 색을 따르게 했더니, 보통 시나리오까지 적자인 날에 굵은
  // 선과 상자는 빨간데 정작 적자 시점을 짚는 점만 호박색으로 남았다.
  // deadPoint 의 시나리오(가장 먼저 무너지는 쪽)와 심각도는 별개다.
  const dead = deadMarker(scenarios, deadPoint);
  const deadColor = midDips ? main : edge;

  return (
    <div className="rounded-2xl bg-gray-50 p-4">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 16, right: 20, bottom: 0, left: 0 }}>
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

          {/* 잔고가 처음 0원 아래로 내려가는 달. 옅은 원을 뒤에 깔아 선 위의
              평범한 점과 구별되게 한다. */}
          {dead !== null && (
            <ReferenceDot
              x={dead.label}
              y={dead.balance}
              r={9}
              fill={deadColor}
              fillOpacity={0.18}
              stroke="none"
            />
          )}
          {dead !== null && (
            <ReferenceDot
              x={dead.label}
              y={dead.balance}
              r={4}
              fill={deadColor}
              stroke="#ffffff"
              strokeWidth={2}
              label={<CrisisLabel color={deadColor} />}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <p className="mt-2 text-center text-[11px] text-gray-400">
        굵은 선은 {SCENARIO_LABEL.NORMAL}, 아래 얇은 선은 {SCENARIO_LABEL.TIGHT}{' '}
        시나리오입니다
        {alternative && ` · 점선은 ${alternative.label}`}
        {deadPoint !== null &&
          ` · 위기는 ${SCENARIO_LABEL[deadPoint.level]} 기준 첫 적자 달`}
      </p>
    </div>
  );
}

/**
 * 위기 표시 말풍선.
 *
 * recharts 가 viewBox 로 점의 화면 좌표를 넣어 준다. 점 바로 옆에 붙여야
 * 어느 달의 일인지 눈으로 이어진다.
 *
 * 기본은 아래다. 적자 지점 바로 위에는 늘 보통 시나리오 선이 지나가서
 * (적자는 가장 아래 선에서 먼저 난다) 위에 달면 굵은 선의 데이터 점을 가린다.
 *
 * 다만 적자가 깊으면 점이 눈금 글자 근처까지 내려와 아래에 달 자리가 없다.
 * 그때만 위로 올린다 — 그 정도로 내려온 점이면 굵은 선은 이미 한참 위에 있다.
 */
function CrisisLabel({
  color,
  viewBox,
}: {
  color: string;
  viewBox?: { x?: number; y?: number };
}) {
  const x = viewBox?.x ?? 0;
  const y = viewBox?.y ?? 0;
  const fitsBelow = y + PILL_OFFSET + PILL_HALF <= PLOT_BOTTOM;
  const dy = fitsBelow ? PILL_OFFSET : -PILL_OFFSET;
  return (
    <g transform={`translate(${x}, ${y + dy})`} style={{ pointerEvents: 'none' }}>
      <rect x={-17} y={-9} width={34} height={18} rx={9} fill={color} />
      <text
        x={0}
        y={0}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={10}
        fontWeight={700}
        fill="#ffffff"
      >
        위기
      </text>
    </g>
  );
}

/**
 * 잔고가 처음 0원 아래로 내려가는 지점.
 *
 * 백엔드가 준 deadPoint 의 시나리오와 달을 그대로 쓴다. 프론트에서 다시
 * 찾으면 적자 판정이 두 곳에 생겨 서로 어긋날 수 있다
 * (forecast/projection.py 의 _find_dead_point 가 유일한 기준이다).
 */
function deadMarker(
  scenarios: Scenario[],
  deadPoint: DeadPoint | null,
): { label: string; balance: number } | null {
  if (deadPoint === null) return null;
  const points = scenarios.find((s) => s.level === deadPoint.level)?.points ?? [];
  const index = points.findIndex((p) => p.month === deadPoint.month);
  if (index < 0) return null;
  return { label: `${index + 1}개월`, balance: points[index].balance };
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
