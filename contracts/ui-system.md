# 넉넉 디자인 시스템

AI로 화면 코드를 생성할 때 이 파일을 반드시 함께 제공한다.
아래 클래스 문자열을 그대로 사용하고 임의로 변형하지 않는다.
"파란 버튼을 쓴다" 같은 서술이 아니라 클래스 조합을 그대로 적은 이유는,
AI가 해석할 여지를 없애 세 사람의 화면이 갈라지지 않게 하기 위해서다.

## 색상

| 용도 | 클래스 |
|---|---|
| 주색 | `text-blue-600` / `bg-blue-600` / `border-blue-600` |
| 주색 진함 (hover) | `bg-blue-700` |
| 주색 옅음 (배경 강조) | `bg-blue-50` |
| 경고 (적자, 부족) | `text-red-600` / `bg-red-50` |
| 성공 (실적 충족, 여유) | `text-emerald-600` / `bg-emerald-50` |
| 주의 (빠듯) | `text-amber-600` / `bg-amber-50` |
| 본문 텍스트 | `text-gray-900` |
| 보조 텍스트 | `text-gray-500` |
| 테두리 | `border-gray-200` |
| 페이지 배경 | `bg-gray-50` |
| 카드 배경 | `bg-white` |

## 시나리오 색상

| 시나리오 | 선 색상 | 텍스트 |
|---|---|---|
| 여유 (COMFORTABLE) | `stroke-emerald-500` | `text-emerald-600` |
| 보통 (NORMAL) | `stroke-blue-600` | `text-blue-600` |
| 빠듯 (TIGHT) | `stroke-amber-500` | `text-amber-600` |

보통(NORMAL)을 기본 강조선으로 하고 나머지는 얇게 그린다.

## 컴포넌트 클래스

### 기본 버튼
```
bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-gray-300
rounded-lg px-4 py-2 text-white text-sm font-medium transition-colors
```

### 보조 버튼
```
bg-white hover:bg-gray-50 border border-gray-300
rounded-lg px-4 py-2 text-gray-700 text-sm font-medium transition-colors
```

### 카드
```
bg-white rounded-xl border border-gray-200 p-6
```

### 강조 카드 (가용잔고 등)
```
bg-blue-50 rounded-xl border border-blue-200 p-6
```

### 입력 필드
```
w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm
focus:border-blue-600 focus:ring-1 focus:ring-blue-600 outline-none
```

### 입력 필드 (오류)
```
w-full rounded-lg border border-red-500 px-4 py-2.5 text-sm
focus:ring-1 focus:ring-red-500 outline-none
```

### 뱃지
```
inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium
```

## 타이포그래피

| 용도 | 클래스 |
|---|---|
| 페이지 제목 | `text-2xl font-bold text-gray-900` |
| 섹션 제목 | `text-lg font-semibold text-gray-900` |
| 본문 | `text-sm text-gray-900` |
| 보조 설명 | `text-sm text-gray-500` |
| 캡션 | `text-xs text-gray-500` |
| 금액 강조 | `text-3xl font-bold tabular-nums` |

## 간격

| 용도 | 클래스 |
|---|---|
| 페이지 좌우 여백 | `px-4 md:px-8` |
| 페이지 최대 너비 | `max-w-5xl mx-auto` |
| 섹션 사이 | `mb-8` |
| 카드 사이 | `gap-4` |
| 카드 내부 요소 사이 | `space-y-4` |
| 라벨과 값 사이 | `mb-1` |

## 표기 규칙

- 금액은 `formatWon` 사용. 예) `1,800,000원`
- 차트 축은 `formatManwon` 사용. 예) `180만`
- 시나리오는 화면에 **여유 / 보통 / 빠듯**으로만 표기한다. 낙관·기본·비관은 내부 용어이므로 노출하지 않는다.
- 날짜는 `M월 D일` 형식. 예) `9월 1일`
- 모든 숫자에 `tabular-nums` 적용 (자릿수 흔들림 방지)
- 시연용 가상 카드에는 반드시 "시연용" 뱃지를 표시한다

## 상태 처리 (필수)

모든 비동기 화면은 아래 세 상태를 반드시 구현한다.

| 상태 | 처리 |
|---|---|
| 로딩 | `animate-pulse bg-gray-200 rounded` 스켈레톤 |
| 오류 | 사용자가 이해할 메시지 + 재시도 버튼. 오류 원문 노출 금지 |
| 빈 값 | 안내 문구 + 다음 행동 유도 |

LLM 응답은 수 초가 걸린다. 로딩 표시가 없으면 시연 중 멈춘 것처럼 보인다.

특히 `explanation` 필드가 `null`인 경우(LLM 생성 실패)에도 **나머지 계산 결과는 정상 표시**해야 한다. 설명만 빠지고 숫자는 나오는 것이 정상 동작이다.

## 반응형

모바일 우선으로 작성하고 `md:` 접두사로 데스크톱을 확장한다.
심사위원이 노트북으로 볼 가능성이 높으므로 데스크톱 레이아웃을 반드시 확인한다.
