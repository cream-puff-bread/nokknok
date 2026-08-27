import type { BalanceResponse } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

export function fetchBalance(
  personaId: number,
  options?: ApiRequestOptions,
): Promise<BalanceResponse> {
  return apiGet<BalanceResponse>(`/api/balance?personaId=${personaId}`, options);
}
