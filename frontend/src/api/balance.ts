import type { BalanceResponse } from '../types/contract';
import { apiGet } from './client';

export function fetchBalance(personaId: number): Promise<BalanceResponse> {
  return apiGet<BalanceResponse>(`/api/balance?personaId=${personaId}`);
}
