# frontend

React + TypeScript + Vite.

## 실행

```bash
npm install
npm run dev
```

## 주의

### 타입은 contracts/types.ts 를 따른다

빌드 전에 계약 파일을 복사해 사용한다.

```json
"scripts": {
  "prebuild": "cp ../contracts/types.ts src/types/contract.ts",
  "build": "vite build"
}
```

응답 구조를 임의로 가정하지 않는다. 필요한 필드가 없으면 화면에서
만들어내지 말고 API 담당자에게 알린다.

### 금액 계산을 하지 않는다

할인액, 잔고, 실적 충족 여부는 모두 백엔드가 계산한 값을 표시만 한다.
프론트에서 재계산하면 백엔드와 값이 어긋난다.
`formatWon`, `formatManwon` 같은 표기 변환만 허용한다.

### 스타일은 contracts/ui-system.md 를 따른다

AI로 화면 코드를 생성할 때 이 파일을 반드시 함께 제공한다.

### explanation 이 null 이어도 결과를 표시한다

LLM 생성 실패 시 `explanation` 은 `null` 이지만 계산 결과는 정상이다.
설명이 없다고 카드 전체를 숨기지 않는다.
