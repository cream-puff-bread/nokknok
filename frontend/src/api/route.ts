import type { RouteResponse } from '../types/contract';
import { apiPost, type ApiRequestOptions } from './client';

export function runRoute(
  personaId: number,
  amount: number,
  category: string,
  options?: ApiRequestOptions,
): Promise<RouteResponse> {
  return apiPost<RouteResponse>('/api/route', { personaId, amount, category }, options);
}
