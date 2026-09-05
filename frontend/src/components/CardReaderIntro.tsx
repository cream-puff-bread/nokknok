import { useEffect, useState } from 'react';
import { animate, motion, useMotionValue, useTransform } from 'framer-motion';

import { BankCard } from './BankCard';
import { Logo } from './Logo';

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
 * 표시창 글자색. 발광은 어두운 표시창 안에서만 쓴다 — 흰 바탕 위의 글로우는
 * 번져 보이기만 하고 켜진 느낌이 안 난다.
 */
const DISPLAY_TEXT_CLASS: Record<Phase, string> = {
  ready: 'text-white/35',
  reading: 'text-amber-400',
  success: 'text-emerald-400',
};

const LAMP_CLASS: Record<Phase, string> = {
  ready: 'bg-gray-600',
  reading: 'bg-amber-400',
  success: 'bg-emerald-400',
};

/** 표시등이 기기 밖으로 번지는 빛. 꺼져 있을 때는 그리지 않는다. */
const LAMP_GLOW_CLASS: Record<Phase, string> = {
  ready: 'opacity-0',
  reading: 'bg-amber-400 opacity-70',
  success: 'bg-emerald-400 opacity-80',
};

/**
 * 카드의 가로 오프셋(기기 중앙이 0). 카드는 기기 왼쪽 위에서 시작해 오른쪽으로
 * 긁어 통과시킨다 — 세로로 떨어뜨리는 리더기가 아니라 가로로 긋는 동작이다.
 *
 * 폭에 따라 치수를 나눈다. 넓은 화면 값을 그대로 쓰면 폰에서 카드가 시작부터
 * 화면 왼쪽 밖으로 반쯤 나가 잘린 채로 보인다. 화면 전체를 축소하는 방법도
 * 있지만, 그러면 손가락을 움직인 거리와 카드가 움직인 거리가 어긋나 끌리는
 * 느낌이 둔해진다.
 */
interface Geometry {
  /** 쉴 때 카드가 기기 중앙에서 왼쪽으로 물러나 있는 거리. */
  startX: number;
  /** 여기까지 끌고 놓으면 성공으로 확정한다. */
  successAt: number;
  /** 성공 후 카드가 기기를 빠져나가 멈추는 지점. */
  throughX: number;
  card: string;
}

const GEOMETRY: Record<'wide' | 'narrow', Geometry> = {
  wide: { startX: -150, successAt: 90, throughX: 240, card: 'h-44 w-72' },
  narrow: { startX: -50, successAt: 40, throughX: 140, card: 'h-36 w-60' },
};

const NARROW_MAX_WIDTH = 640;
const READ_THRESHOLD = 0;

/**
 * 쉴 때 카드가 기기보다 위에 떠 있는 높이.
 *
 * 카드를 기기와 같은 높이에 두면 시작부터 절반이 기기에 가려 무엇을 끌어야
 * 하는지 안 보인다. 위에 띄워 두고 끌수록 내려와 기기 뒤로 들어가게 하면,
 * 가로로만 미는데도 "집어서 긁는" 동작으로 읽힌다.
 */
const REST_Y = -90;

/**
 * 기기를 무대 중앙보다 아래로 내리는 거리.
 *
 * 둘 다 중앙에 두면 쉴 때부터 카드 아래쪽이 기기에 걸쳐 있어, 통과하기 전에
 * 이미 겹쳐 있는 모양이 된다. 기기를 내리고 카드를 띄워 둘을 완전히 떼어
 * 놓아야 "아직 안 긁었다" 가 한눈에 보인다.
 */
const READER_DROP = 70;

// 성공 후 타임라인: SUCCESS 를 잠깐 보여준 뒤 화면을 위로 밀며 페이드아웃하고,
// 그게 끝나야 실제 라우팅이 일어난다 — 카드와 기기가 뚝 끊기지 않고 사라지며
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
 * 카드를 긁어 들어가는 진입 연출. 원안은 #38(팀원 작업)이다.
 *
 * 원안은 슬롯을 얇은 가로선으로 두고 표시창을 그 아래 따로 놓았는데, 그러면
 * 카드가 아무것도 아닌 선 위를 지나가고 옆에서 다른 상자가 READY 라고 말하는
 * 모양이 된다. 기기를 입체로 세우고 카드가 그 **뒤로** 지나가게 하면 통과하는
 * 것처럼 보인다 — 카드가 기기에 가려지는 순간이 곧 읽히는 순간이다.
 *
 * 색은 대시보드에 맞췄고 다크 모드와 외부 CDN 폰트는 가져오지 않는다. 나머지
 * 화면에 dark: 대응이 하나도 없어서 이 화면만 어두우면 넘어가는 순간 톤이 튄다.
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

  // 여는 순간의 폭으로 한 번만 정한다. 연출이 도는 몇 초 사이에 창 크기를
  // 바꾸는 경우까지 따라가면 드래그 중에 카드가 튄다.
  const [size] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth < NARROW_MAX_WIDTH
      ? GEOMETRY.narrow
      : GEOMETRY.wide,
  );

  const x = useMotionValue(size.startX);
  // 기기에 닿기 전에 다 내려와 있어야 뒤로 들어가는 것처럼 보인다.
  const y = useTransform(x, [size.startX, -40], [REST_Y, 0]);
  // 손으로 긋는 카드는 수평을 유지하지 않는다. 각도를 조금 주면 뻣뻣함이 준다.
  const rotate = useTransform(x, [size.startX, size.throughX], [-3, 5]);

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
    if (x.get() >= size.successAt) {
      setLocked(true);
      setPhase('success');
      animate(x, size.throughX, { type: 'spring', stiffness: 260, damping: 26 });
      setTimeout(() => setExiting(true), SUCCESS_HOLD_MS);
      setTimeout(onComplete, SUCCESS_HOLD_MS + EXIT_MS);
      return;
    }
    setPhase('ready');
    animate(x, size.startX, { type: 'spring', stiffness: 320, damping: 30 });
  };

  return (
    <motion.div
      animate={{ opacity: exiting ? 0 : 1, y: exiting ? -32 : 0 }}
      transition={{ duration: EXIT_MS / 1000, ease: 'easeIn' }}
      className="relative flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4"
    >
      {/* 심사위원이 맨 처음 보는 화면인데 카드 면의 로고 말고는 이 서비스가
          무엇인지 말하는 것이 없었다. 헤더에 쓰는 문장을 그대로 얹는다. */}
      <div className="flex flex-col items-center text-center">
        <Logo />
        <p className="mt-1 text-sm text-gray-500">
          이미 나갈 돈을 뺀 진짜 쓸 수 있는 잔고와, 어느 카드로 결제할지 계산해 드립니다
        </p>
      </div>

      {/* 카드와 기기를 한 무대에 겹쳐 놓는다. 카드가 기기보다 뒤(z 가 낮음)에
          있어야 끌었을 때 가려지고, 그 가려짐이 통과처럼 읽힌다. */}
      {/* overflow-hidden 은 카드가 오른쪽으로 빠져나갈 때 페이지에 가로
          스크롤이 생기는 것을 막는다. 빠져나가며 잘리는 것은 맞는 모양이다.
          다만 무대가 좁으면 쉴 때부터 카드 왼쪽이 잘려서, 시작 위치가 들어갈
          만큼은 넓혀 둬야 한다. */}
      <div className="relative mt-6 flex h-[440px] w-full max-w-3xl items-center justify-center overflow-hidden">
        <ReaderShell phase={phase} layer="back" />

        <motion.div
          drag={locked ? false : 'x'}
          dragConstraints={{ left: size.startX, right: size.throughX }}
          dragElastic={0.06}
          dragMomentum={false}
          onDrag={handleDrag}
          onDragEnd={handleDragEnd}
          style={{ x, y, rotate, touchAction: 'none' }}
          className={`absolute z-20 cursor-grab drop-shadow-2xl select-none active:cursor-grabbing ${size.card}`}
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

        <ReaderShell phase={phase} layer="front" />
      </div>

      <p className="mt-8 h-5 text-center text-sm text-gray-500">{PHASE_CAPTION[phase]}</p>

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

/**
 * 카드결제기 본체. 뒤판과 앞판을 따로 그린다.
 *
 * 통째로 한 겹으로 두면 카드는 기기 "뒤" 를 지날 수밖에 없어서, 통과가 아니라
 * 가려졌다 나오는 것으로 보인다. 뒤판을 앞판보다 위로 올려 두 판 사이에 틈을
 * 만들고 카드를 그 사이(z-20)에 넣으면, 카드 아랫부분은 앞판에 가리고 윗부분은
 * 뒤판 앞에 놓여 실제로 슬롯에 꽂힌 모양이 된다.
 *
 * 두 겹을 같은 DOM 구조로 그리고 각자 제 몫이 아닌 쪽만 invisible 로 숨긴다.
 * 레이아웃이 완전히 같아야 두 판이 한 기기로 맞물리는데, 구조를 따로 짜면
 * 폭이나 패딩이 조금만 어긋나도 틈이 벌어져 보인다.
 *
 * 사진 한 장 없이 기기처럼 보이게 하는 것은 세 가지다 — 뒤판을 밝게 세워
 * 두께를 만들고, 아래로 긴 그림자를 깔아 벽에서 떠 있게 하고, 표시창만
 * 어둡게 파 넣는 것.
 */
function ReaderShell({ phase, layer }: { phase: Phase; layer: 'back' | 'front' }) {
  const back = layer === 'back';

  return (
    <div
      className={`absolute top-1/2 left-1/2 w-[400px] max-w-full ${back ? 'z-10' : 'z-30'}`}
      style={{ transform: `translate(-50%, calc(-50% + ${READER_DROP}px))` }}
    >
      {/* 뒤판. 앞판보다 위로 나와 있는 이 띠가 카드가 꽂히는 자리다. */}
      <div
        aria-hidden={!back}
        className={`mx-3 h-16 rounded-t-2xl bg-gradient-to-b from-gray-100 via-white to-gray-50 ring-1 ring-gray-200/80 ${
          back ? '' : 'invisible'
        }`}
      />

      {/* 앞판. 뒤판 위로 겹쳐 올려 둘이 한 몸으로 보이게 한다. */}
      <div
        aria-hidden={back}
        className={`-mt-9 rounded-2xl bg-gradient-to-b from-gray-50 via-white to-gray-200 p-4 shadow-[0_28px_50px_-18px_rgba(15,23,42,0.5)] ring-1 ring-gray-300/60 ${
          back ? 'invisible' : ''
        }`}
      >
        <div className="flex items-center gap-4">
          <div className="flex-1 rounded-lg bg-[#0f1216] px-5 py-3.5 shadow-[inset_0_2px_6px_rgba(0,0,0,0.55)]">
            <span
              className={`block text-center font-mono text-lg font-bold tracking-[0.3em] transition-colors ${DISPLAY_TEXT_CLASS[phase]}`}
              // 세그먼트 표시창의 번짐. 글자 자체가 빛나야 LED 로 읽힌다.
              style={{ textShadow: phase === 'ready' ? 'none' : '0 0 14px currentColor' }}
            >
              {READER_DISPLAY[phase]}
            </span>
          </div>

          <span className="relative flex h-6 w-6 shrink-0 items-center justify-center">
            <span
              aria-hidden
              className={`absolute -inset-2 rounded-full blur-lg transition-opacity duration-300 ${LAMP_GLOW_CLASS[phase]}`}
            />
            <span
              className={`relative h-4 w-4 rounded-full ring-1 ring-black/10 transition-colors duration-300 ${LAMP_CLASS[phase]}`}
            />
          </span>
        </div>
      </div>
    </div>
  );
}
