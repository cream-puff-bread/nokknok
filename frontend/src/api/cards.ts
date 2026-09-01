import type { OwnedCard } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

export function fetchOwnedCards(
  personaId: number,
  options?: ApiRequestOptions,
): Promise<OwnedCard[]> {
  return apiGet<OwnedCard[]>(`/api/cards?personaId=${personaId}`, options);
}
