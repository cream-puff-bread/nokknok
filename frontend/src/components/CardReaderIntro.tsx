import { useEffect, useState } from 'react';
import { animate, motion, useMotionValue } from 'framer-motion';

import { BankCard } from './BankCard';

type Phase = 'ready' | 'reading' | 'success';

const PHASE_CAPTION: Record<Phase, string> = {
  ready: '카드를 오른쪽으로 스윽 긁어주세요',
  reading: '카드를 인식하는 중입니다',
  success: '입장 완료',
};

const READER_DISPLAY: Record<Phase, string> = {
  ready: 'READY',
  reading: 'READING',
  success: 'SUCCESS',
};

/**
 * 표시등. 화면 전체가 밝은 톤이라 발광은 어두운 디스플레이 안에서만 쓴다 —
 * 흰 바탕 위의 글로우는 번져 보이기만 하고 켜진 느낌이 안 난다.
 */
const INDICATOR_CLASS: Record<Phase, string> = {
  ready: 'bg-white/20',
  reading: 'bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.7)]',
  success: 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]',
};

const DISPLAY_TEXT_CLASS: Record<Phase, string> = {
  ready: 'text-white/40',
  reading: 'text-amber-400',
  success: 'text-emerald-400',
};

// x는 카드결제기 슬롯 중앙을 0으로 둔 상대 오프셋이다. 카드는 슬롯 왼쪽에서
// 시작해 오른쪽으로 긁어 통과시킨다 — 세로로 떨어뜨리는 리더기가 아니라
// 가로로 긋는 카드결제기 동작이다.
const START_X = -90;
const READ_THRESHOLD = 0;
const SUCCESS_THRESHOLD = 70;
const THROUGH_X = 170;
const DRAG_CONSTRAINTS = { left: START_X, right: THROUGH_X };

// 성공 후 타임라인: SUCCESS 를 잠깐 보여준 뒤 화면을 위로 밀며 페이드아웃하고,
// 그게 끝나야 실제 라우팅이 일어난다 — 카드와 결제기가 뚝 끊기지 않고 사라지며
// 넘어가게 한다.
const SUCCESS_HOLD_MS = 600;
const EXIT_MS = 500;

/**
 * 끌지 못하는 사람에게 건너뛰기를 내보이기까지 기다리는 시간.
 *
 * 처음부터 눈에 띄게 두면 연출을 보기도 전에 지나치는 쪽이 많아지고, 끝까지
 * 숨겨 두면 드래그가 안 되는 환경에 걸린 사람이 제품을 하나도 못 본 채 나간다.
 */
const SKIP_REVEAL_MS = 3000;

interface CardReaderIntroProps {
  /** 카드를 끝까지 긁거나 건너뛰면 호출된다. 실제 인증과는 무관한 순수 진입
   * 연출이다 — 이 앱에는 로그인 개념이 없다. */
  onComplete: () => void;
}

/**
 * 카드를 긁어 들어가는 진입 연출. 원안은 #38(팀원 작업)이고 여기서는 색만
 * 대시보드에 맞췄다 — 다크 모드와 외부 CDN 폰트는 가져오지 않는다. 나머지
 * 화면에 다크 대응이 하나도 없어서, 그것만 어두우면 넘어가는 순간 톤이 튄다.
 *
 * 연출로만 두면 심사위원이 제품을 보기까지 한 단계가 더 생길 뿐이다. 이 화면이
 * 값을 하는 지점은 따로 있다 — Render 가 15분이면 잠들어 첫 요청이 30~60초
 * 걸리는데, 그 시간을 여기서 미리 쓴다(routes.tsx 의 프리페치).
 */
export function CardReaderIntro({ onComplete }: CardReaderIntroProps) {
  const [phase, setPhase] = useState<Phase>('ready');
  const [locked, setLocked] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [skipShown, setSkipShown] = useState(false);
  const x = useMotionValue(START_X);

  useEffect(() => {
    const timer = setTimeout(() => setSkipShown(true), SKIP_REVEAL_MS);
    return () => clearTimeout(timer);
  }, []);

  const handleDrag = () => {
    if (locked) return;
    setPhase(x.get() > READ_THRESHOLD ? 'reading' : 'ready');
  };

  const handleDragEnd = () => {
    if (locked) return;
    if (x.get() >= SUCCESS_THRESHOLD) {
      setLocked(true);
      setPhase('success');
      animate(x, THROUGH_X, { type: 'spring', stiffness: 260, damping: 26 });
      setTimeout(() => setExiting(true), SUCCESS_HOLD_MS);
      setTimeout(onComplete, SUCCESS_HOLD_MS + EXIT_MS);
      return;
    }
    setPhase('ready');
    animate(x, START_X, { type: 'spring', stiffness: 320, damping: 30 });
  };

  return (
    <motion.div
      animate={{ opacity: exiting ? 0 : 1, y: exiting ? -32 : 0 }}
      transition={{ duration: EXIT_MS / 1000, ease: 'easeIn' }}
      className="relative flex min-h-screen flex-col items-center justify-center gap-6 bg-gray-50 px-4"
    >
      {/* 심사위원이 맨 처음 보는 화면인데 카드 면의 로고 말고는 이 서비스가
          무엇인지 말하는 것이 없었다. 헤더에 쓰는 문장을 그대로 얹는다. */}
      <div className="mb-2 text-center">
        <p className="text-2xl font-bold text-gray-900">넉넉</p>
        <p className="mt-1 text-sm text-gray-500">
          이미 나갈 돈을 뺀 진짜 쓸 수 있는 잔고와, 어느 카드로 결제할지 계산해 드립니다
        </p>
      </div>

      {/* 슬롯과 카드가 겹치는 긁는 영역. 같은 컨테이너 안에서 둘 다 세로
          중앙에 있어 카드가 슬롯 위를 정확히 지나가는 것처럼 보인다. */}
      <div className="relative flex h-48 w-80 items-center justify-center">
        {/* 슬롯은 카드보다 눈에 띄게 길어야 한다. 카드 폭과 비슷하면 드래그
            내내 카드에 가려 양옆 조각만 보인다. shrink-0 이 없으면 flex 안에서
            지정 폭이 무시되고 컨테이너 폭까지 줄어든다. */}
        <div className="h-2.5 w-[480px] max-w-[90vw] shrink-0 rounded-full bg-gray-200" />

        <motion.div
          drag={locked ? false : 'x'}
          dragConstraints={DRAG_CONSTRAINTS}
          dragElastic={0.06}
          dragMomentum={false}
          onDrag={handleDrag}
          onDragEnd={handleDragEnd}
          style={{ x, touchAction: 'none' }}
          // 원안은 성공 시 0.4까지 흐렸다. 어두운 배경에서는 카드가 어둠으로
          // 물러나는 것처럼 보이지만, 밝은 배경에서는 그냥 비활성된 요소로
          // 읽힌다. 여기서는 살짝만 낮추고 퇴장 애니메이션이 데려가게 둔다.
          animate={{ opacity: phase === 'success' ? 0.85 : 1, rotate: phase === 'success' ? 2 : 0 }}
          className="absolute top-1/2 left-1/2 -mt-[88px] -ml-[144px] h-44 w-72 cursor-grab select-none active:cursor-grabbing"
        >
          <BankCard
            className="h-full w-full rounded-3xl"
            surface="bg-slate-700"
            accent="#6366f1"
            brand="NOKKNOK"
            subtitle="Access Pass"
            title="GUEST USER"
          />
        </motion.div>
      </div>

      {/* 결제기 본체는 흰 카드, 디스플레이만 어둡게 둔다. 기기의 표시창은
          원래 어둡고, 카드 면과 톤이 이어져 둘이 한 세트로 읽힌다. */}
      <div className="w-72 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between rounded-md bg-gray-900 px-4 py-3">
          <span
            className={`text-sm font-bold tracking-wide transition-colors ${DISPLAY_TEXT_CLASS[phase]}`}
          >
            {READER_DISPLAY[phase]}
          </span>
          <span
            className={`h-2.5 w-2.5 rounded-full transition-colors ${INDICATOR_CLASS[phase]}`}
          />
        </div>
      </div>

      <p className="h-5 text-center text-xs tracking-wide text-gray-500">
        {PHASE_CAPTION[phase]}
      </p>

      <button
        type="button"
        onClick={onComplete}
        className={`absolute bottom-8 rounded-full border border-gray-200 bg-white px-4 py-2 text-xs text-gray-500 transition-opacity hover:text-gray-900 ${
          skipShown ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      >
        건너뛰고 바로 보기
      </button>
    </motion.div>
  );
}
