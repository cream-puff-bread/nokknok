import { useEffect, useState } from 'react';

import type { SpendCategory } from '../types/contract';
import { apiGet, type ApiRequestOptions } from './client';

export function fetchCategories(options?: ApiRequestOptions): Promise<SpendCategory[]> {
  return apiGet<SpendCategory[]>('/api/categories', options);
}

/**
 * spend_category 코드를 화면 표기로 바꾸는 함수를 돌려준다.
 *
 * 대응표를 화면에 두지 않는 이유는 frontend/README.md 에 적어둔 것과 같다 —
 * 카테고리를 추가할 때 고쳐야 할 곳이 DB 와 프론트 두 군데가 되고, 한 곳을
 * 빠뜨리면 조용히 어긋난다.
 *
 * 목록을 못 받아왔거나 모르는 코드가 오면 코드를 그대로 돌려준다. 라벨은
 * 읽기 편하라고 붙이는 것이지 결과 자체가 아니다. 라벨이 없다고 화면이
 * 비면 안 된다(explanation 이 null 이어도 계산 결과를 표시하는 것과 같은 이유다).
 */
export function useCategoryLabels(): (code: string) => string {
  const [labels, setLabels] = useState<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    fetchCategories()
      .then((categories) => {
        if (!alive) return;
        setLabels(Object.fromEntries(categories.map((c) => [c.code, c.label])));
      })
      // 라벨 조회 실패는 화면을 막을 이유가 아니다. 코드를 그대로 보여준다.
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  return (code: string) => labels[code] ?? code;
}
