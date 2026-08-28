import type { Persona } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

export function fetchPersonas(options?: ApiRequestOptions): Promise<Persona[]> {
  return apiGet<Persona[]>('/api/personas', options);
}
