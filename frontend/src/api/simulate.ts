import type { SimulationResponse } from '../types/contract';
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
