import type { Persona } from '../types/contract';
import { apiGet } from './client';

export function fetchPersonas(): Promise<Persona[]> {
  return apiGet<Persona[]>('/api/personas');
}
