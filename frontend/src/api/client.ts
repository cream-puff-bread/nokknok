// 공용 fetch 헬퍼. 상대경로로 호출해 Vite 프록시를 탄다(frontend/README.md 참고).
import type { ApiError, ApiErrorCode } from '../types/contract';

export class ApiRequestError extends Error {
  readonly code: ApiErrorCode;

  constructor(code: ApiErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

// 백엔드 오류 응답은 항상 {code, message} 형태다(contracts/api-spec.yaml
// ErrorResponse). 본문을 못 읽거나 형식이 다르면(순수 네트워크 실패 등)
// message 문구로 분기하지 않도록 code는 INTERNAL_ERROR로 고정한다.
async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  const body = (await response.json().catch(() => null)) as ApiError | null;
  return new ApiRequestError(
    body?.code ?? 'INTERNAL_ERROR',
    body?.message ?? '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  );
}

export async function apiGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path);
  } catch {
    // 네트워크 자체가 끊긴 경우. 서버가 준 code가 없으므로 INTERNAL_ERROR로 다룬다.
    throw new ApiRequestError('INTERNAL_ERROR', '서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    throw await toApiRequestError(response);
  }
  return (await response.json()) as T;
}
