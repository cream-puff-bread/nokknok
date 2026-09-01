import type { ParsedQuery, SimulationResponse } from '../types/contract';
import { apiPost, type ApiRequestOptions } from './client';

/** 질의 길이 상한. contracts/api-spec.yaml 의 maxLength 와 같은 값이다. */
export const MAX_QUERY_LENGTH = 200;

export function runSimulation(
  personaId: number,
  query: string,
  options?: ApiRequestOptions,
): Promise<SimulationResponse> {
  return apiPost<SimulationResponse>('/api/simulate', { personaId, query }, options);
}

/**
 * 결제 라우팅에서 넘어온 구매를 그대로 시뮬레이션한다.
 *
 * 이미 정확히 아는 값을 문장으로 만들어 서버가 다시 해석하게 하지 않는다 —
 * 해석이 어긋나면 두 화면이 서로 다른 숫자를 말하게 된다. 서버가 LLM 을
 * 건너뛰므로 응답도 2.2초에서 0.8초로 줄어든다.
 */
export function runSimulationForPurchase(
  personaId: number,
  purchase: ParsedQuery,
  options?: ApiRequestOptions,
): Promise<SimulationResponse> {
  return apiPost<SimulationResponse>('/api/simulate', { personaId, purchase }, options);
}
