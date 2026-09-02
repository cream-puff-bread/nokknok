import { useState } from 'react';
import { animate, motion, useMotionValue } from 'framer-motion';

import { BankCard } from './BankCard';
import { ThemeToggle } from '../theme/ThemeToggle';

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

const INDICATOR_CLASS: Record<Phase, string> = {
  ready: 'bg-gray-300 dark:bg-white/20',
  reading: 'bg-amber-400 shadow-[0_0_12px_theme(colors.amber.300)]',
  success: 'bg-emerald-400 shadow-[0_0_12px_theme(colors.emerald.300)]',
};

// x는 "카드결제기" 슬롯 중앙을 0으로 둔 상대 오프셋이다. 카드는 슬롯 왼쪽에서
// 시작해 오른쪽으로 긁어(swipe) 통과시킨다 — 세로로 떨어뜨리는 리더기가
// 아니라 가로로 긋는 카드결제기 동작이다.
const START_X = -90;
const READ_THRESHOLD = 0; // 슬롯 중앙을 지나면 "인식 중"
const SUCCESS_THRESHOLD = 70; // 여기서 놓으면 성공으로 확정
const THROUGH_X = 170; // 성공 시 카드가 슬롯을 완전히 빠져나가 멈추는 지점
const DRAG_CONSTRAINTS = { left: START_X, right: THROUGH_X };

interface CardReaderIntroProps {
  /** 카드를 끝까지 긁거나 Skip을 누르면 호출된다. 실제 인증과는 무관한
   * 순수 진입 연출이다 — 지금 앱에는 로그인 개념이 없다. */
  onComplete: () => void;
}

// 성공 후 타임라인: SUCCESS 표시를 잠깐 보여준 뒤(HOLD_MS) 화면 전체를
// 위로 살짝 밀며 페이드아웃(EXIT_MS)하고, 그게 끝나야 실제 라우팅이
// 일어난다 — 카드/결제기가 다른 페이지로 뚝 끊기지 않고 부드럽게 사라지며
// 넘어가는 것처럼 보이게 하기 위해서다(기획안 "4. 화면 전환" 요구사항).
const SUCCESS_HOLD_MS = 600;
const EXIT_MS = 500;

export function CardReaderIntro({ onComplete }: CardReaderIntroProps) {
  const [phase, setPhase] = useState<Phase>('ready');
  const [locked, setLocked] = useState(false);
  const [exiting, setExiting] = useState(false);
  const x = useMotionValue(START_X);

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
      className="relative min-h-screen bg-white dark:bg-ink flex flex-col items-center justify-center gap-10 px-4"
    >
      <div className="absolute top-6 left-6">
        <ThemeToggle />
      </div>
      {/* 카드결제기 슬롯 + 카드가 겹치는 스윽 긁는 영역. 같은 컨테이너
          안에서 둘 다 세로 중앙 정렬돼 있어 카드가 슬롯 위를 정확히
          지나가는 것처럼 보인다. */}
      <div className="relative w-80 h-48 flex items-center justify-center">
        {/* 슬롯은 카드보다 눈에 띄게 길어야 한다 — 카드 폭(w-72=288px)과
            거의 같으면 드래그 내내 카드에 가려 양옆으로 삐져나온 조각만
            보이는 어색한 모양이 된다(실측 확인). */}
        {/* shrink-0 필수: flex 컨테이너 안에서 기본 flex-shrink:1 때문에
            480px 지정이 무시되고 컨테이너 폭(320px)까지 줄어드는 문제가
            실제로 있었다(스크린샷으로 확인). */}
        <div className="w-[480px] max-w-[90vw] h-2.5 rounded-full bg-gray-200 dark:bg-white/15 shrink-0" />

        <motion.div
          drag={locked ? false : 'x'}
          dragConstraints={DRAG_CONSTRAINTS}
          dragElastic={0.06}
          dragMomentum={false}
          onDrag={handleDrag}
          onDragEnd={handleDragEnd}
          style={{ x, touchAction: 'none' }}
          animate={{ opacity: phase === 'success' ? 0.4 : 1, rotate: phase === 'success' ? 2 : 0 }}
          className="absolute top-1/2 left-1/2 w-72 h-44 -ml-[144px] -mt-[88px] cursor-grab active:cursor-grabbing select-none"
        >
          <BankCard
            className="h-full w-full"
            accent="#6366f1"
            brand="NOKKNOK"
            subtitle="Access Pass"
            title="GUEST USER"
          />
        </motion.div>
      </div>

      <div className="w-72 rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 shadow-md p-4">
        <div className="rounded-md bg-black/40 border border-gray-200 dark:border-white/5 px-4 py-3 flex items-center justify-between">
          <span
            className={`text-sm font-bold tracking-wide transition-colors ${
              phase === 'success'
                ? 'text-emerald-400'
                : phase === 'reading'
                  ? 'text-amber-400'
                  : 'text-gray-400 dark:text-white/40'
            }`}
          >
            {READER_DISPLAY[phase]}
          </span>
          <span className={`h-2.5 w-2.5 rounded-full transition-colors ${INDICATOR_CLASS[phase]}`} />
        </div>
      </div>

      <p className="h-5 text-xs text-gray-500 dark:text-white/60 uppercase tracking-wide text-center">
        {PHASE_CAPTION[phase]}
      </p>

      <button
        type="button"
        onClick={onComplete}
        className="absolute bottom-6 right-6 text-xs text-gray-400 dark:text-white/40 uppercase tracking-wide hover:text-gray-900 dark:hover:text-white"
      >
        Skip
      </button>
    </motion.div>
  );
}
