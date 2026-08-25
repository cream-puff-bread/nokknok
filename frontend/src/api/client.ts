// 공용 fetch 헬퍼. 상대경로로 호출해 Vite 프록시를 탄다(frontend/README.md 참고).
import type { ApiError, ApiErrorCode } from '../types/contract';

export class ApiRequestError extends Error {
  readonly code: ApiErrorCode;

  constructor(code: ApiErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

// 백엔드 오류 응답은 항상 {code, message} 형태다(contracts/api-spec.yaml
// ErrorResponse). 본문을 못 읽거나 형식이 다르면(순수 네트워크 실패 등)
// message 문구로 분기하지 않도록 code는 INTERNAL_ERROR로 고정한다.
async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  const body = (await response.json().catch(() => null)) as ApiError | null;
  return new ApiRequestError(
    body?.code ?? 'INTERNAL_ERROR',
    body?.message ?? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  );
}

// ─────────────────────────────────────────────
// 콜드스타트 안내
// ─────────────────────────────────────────────
// Render 콜드스타트 + Neon 자동 정지 해제가 겹치면 첫 API 호출이 최대 36초까지
// 걸린다(실측 32.6초). 그동안 스켈레톤만 계속 돌면 멈춘 것처럼 보인다
// (contracts/ui-system.md "로딩" 규칙 — 표시가 없으면 멈춘 것처럼 보인다).
//
// 타임아웃은 걸지 않는다. 36초 걸려도 결국 성공하는 편이, 30초에 끊고
// 오류를 내는 것보다 낫다 — 심사 중 "고장난 서비스"로 보이는 것을 막는 게
// 목적이지, 응답을 강제로 끝내는 게 목적이 아니다.
export type SlowRequestPhase = 'WAKING' | 'STILL_WAKING';

export const SLOW_REQUEST_MESSAGE: Record<SlowRequestPhase, string> = {
  WAKING: '서버를 준비하는 중입니다.',
  STILL_WAKING: '조금만 더 기다려 주세요. 최초 접속 시 서버 기동에 시간이 걸립니다.',
};

const WAKING_DELAY_MS = 5_000;
const STILL_WAKING_DELAY_MS = 15_000;

export interface ApiGetOptions {
  /**
   * 요청이 5초·15초 문턱을 넘기면 각각 한 번씩 호출된다.
   *
   * 콜백으로 넘기는 이유는 이 파일이 React를 몰라도 되게 하기 위해서다 —
   * 화면(컴포넌트)이 자기 state를 이 콜백 안에서 갱신하므로, api/client.ts는
   * 타이머만 관리하고 렌더링에는 관여하지 않는다. 어느 화면에서든 같은
   * 방식(onSlowRequest를 넘기고 phase를 state로 받기)으로 재사용할 수 있다.
   */
  onSlowRequest?: (phase: SlowRequestPhase) => void;
}

export async function apiGet<T>(path: string, options?: ApiGetOptions): Promise<T> {
  const timers: ReturnType<typeof setTimeout>[] = [];
  const onSlowRequest = options?.onSlowRequest;
  if (onSlowRequest) {
    timers.push(setTimeout(() => onSlowRequest('WAKING'), WAKING_DELAY_MS));
    timers.push(setTimeout(() => onSlowRequest('STILL_WAKING'), STILL_WAKING_DELAY_MS));
  }

  let response: Response;
  try {
    response = await fetch(path);
  } catch {
    // 네트워크 자체가 끊긴 경우. 서버가 준 code가 없으므로 INTERNAL_ERROR로 다룬다.
    throw new ApiRequestError('INTERNAL_ERROR', '서버에 연결할 수 없습니다.');
  } finally {
    // 응답이 왔든 실패했든, 아직 안 울린 타이머는 더 이상 의미가 없다.
    timers.forEach(clearTimeout);
  }
  if (!response.ok) {
    throw await toApiRequestError(response);
  }
  return (await response.json()) as T;
}
