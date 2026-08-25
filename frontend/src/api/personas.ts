import type { Persona } from '../types/contract';
import { apiGet, type ApiGetOptions } from './client';

export function fetchPersonas(options?: ApiGetOptions): Promise<Persona[]> {
  return apiGet<Persona[]>('/api/personas', options);
}
