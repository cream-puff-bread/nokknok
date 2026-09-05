import type { Persona } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

export function fetchPersonas(options?: ApiRequestOptions): Promise<Persona[]> {
  return apiGet<Persona[]>('/api/personas', options);
}

/**
 * 첫 화면에 보여줄 기본 사례.
 *
 * "가상 인물 셋 중 하나를 고르세요" 로 시작하면 서비스가 아니라 데모로 읽힌다.
 * 로그인한 내 대시보드처럼 바로 들어가고, 사례 전환은 헤더의 계정 전환처럼
 * 부차적으로 둔다.
 *
 * 할부형을 고른 이유는 숫자가 이 서비스의 주장을 그대로 말하기 때문이다 —
 * 통장에 160만원이 있는데 실제로 쓸 수 있는 건 30만원이다. 구독형은
 * 245만 -> 214만이라 차이가 느껴지지 않고, 안정형은 거의 차이가 없다.
 */
export const DEFAULT_PERSONA_ID = 2;

/**
 * 페르소나 목록은 헤더가 매 화면에서 쓴다. 레이아웃이 라우트마다 다시
 * 마운트되므로(#32) 화면을 옮길 때마다 다시 부르지 않도록 한 번만 받아 둔다.
 * 시연 중에는 목록이 바뀌지 않는다.
 */
let cached: Promise<Persona[]> | null = null;

export function loadPersonasOnce(): Promise<Persona[]> {
  cached ??= fetchPersonas().catch((err) => {
    // 실패를 캐시하면 영영 복구되지 않는다. 다음 호출에서 다시 시도한다.
    cached = null;
    throw err;
  });
  return cached;
}
