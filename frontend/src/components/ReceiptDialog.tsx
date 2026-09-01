import { useEffect, useRef, type ReactNode } from 'react';

interface ReceiptDialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/**
 * 결과를 띄우는 가운데 모달.
 *
 * 답이 나왔는데 그 아래로 카드 덱과 확정 지출이 계속 이어지면 무엇이 답인지가
 * 흐려진다. 결제 확인창처럼 앞으로 끌어내 한 가지만 보게 한다.
 *
 * 직접 만들지 않고 <dialog> 를 쓴다. 포커스 가두기, Escape 로 닫기, 바깥
 * 클릭, 배경 스크롤 잠금이 브라우저 기본 동작이라 손으로 구현하면 빠뜨리기
 * 쉽다 — 어설픈 모달은 아예 안 쓰느니만 못하다.
 *
 * 닫아도 결과는 페이지에 남는다. 실수로 닫았다고 계산을 다시 하게 만들지 않는다.
 */
export function ReceiptDialog({ open, onClose, children }: ReceiptDialogProps) {
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();

    // showModal 은 바깥을 조작 불가로 만들지만 배경 스크롤까지 막지는 않는다.
    // 모달 뒤로 페이지가 밀려 내려가면 닫았을 때 엉뚱한 위치에 서 있게 된다.
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      // 바깥(백드롭)을 누르면 닫는다. dialog 자신이 클릭 대상일 때가
      // 백드롭이고, 안쪽 내용은 자식이라 여기까지 올라오지 않는다.
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      aria-label="결제 시뮬레이션 결과"
      className="m-auto w-[min(48rem,92vw)] max-h-[88vh] overflow-y-auto rounded-2xl border border-gray-200 bg-white p-0 shadow-2xl backdrop:bg-black/50"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h2 className="text-lg font-semibold text-gray-900">이 결제, 해도 될까요</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="rounded-lg px-3 py-1.5 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900"
        >
          닫기
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
