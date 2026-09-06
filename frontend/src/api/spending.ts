import type { SpendingSummary } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

/**
 * 한 달치 카테고리별 소비.
 *
 * month 를 생략하면 서버가 거래가 있는 마지막 달을 고른다. 화면에서 "지난달"
 * 같은 상대 표현으로 직접 계산하지 않는 이유는 contracts/api-spec.yaml 에
 * 적힌 것과 같다 — 기준이 실제 날짜에 묶이면 날이 갈수록 빈 달을 가리킨다.
 * 표기는 응답의 month 를 그대로 쓴다.
 */
export function fetchSpending(
  personaId: number,
  month?: string,
  options?: ApiRequestOptions,
): Promise<SpendingSummary> {
  const query = month === undefined ? '' : `&month=${month}`;
  return apiGet<SpendingSummary>(`/api/spending?personaId=${personaId}${query}`, options);
}
