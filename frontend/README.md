# frontend

React 19 + TypeScript 5.9 + Vite 8 + Tailwind CSS 4 + Recharts 3.

## 실행

**Node 20.19+ 또는 22.12+** 가 필요하다(`.nvmrc` 는 22). Vite 8 과
`@vitejs/plugin-react` 가 요구하는 하한이며, `.npmrc` 의 `engine-strict=true`
로 설치 단계에서 막는다. 경고만 띄우고 넘어가면 `npm run dev` 단계에서
원인을 알기 어려운 형태로 깨진다.

```bash
npm install
npm run dev      # http://localhost:5173
```

| 스크립트 | 내용 |
|---|---|
| `npm run dev` | 개발 서버. `/api` 요청은 `http://localhost:8000` 으로 프록시된다 |
| `npm run build` | 타입 검사 후 프로덕션 빌드 |
| `npm run typecheck` | 타입 검사만 |
| `npm run sync:contract` | 계약 타입 사본 갱신 |

## 주의

### 타입은 contracts/types.ts 를 따른다

`contracts/types.ts` 가 단일 원본이며, `src/types/contract.ts` 는 그 사본이다.
사본은 `postinstall` · `predev` · `prebuild` 에서 자동 생성되므로 커밋하지 않는다
(`.gitignore`). 사본을 직접 고치면 다음 실행에서 덮어써지므로, 타입을 바꿔야 하면
`contracts/types.ts` 를 고치고 전원에게 알린다.

복사는 `scripts/copy-contract.mjs` 가 수행한다. `cp` 를 package.json 에 직접 적으면
npm 이 스크립트를 `cmd.exe` 로 실행하는 Windows 에서만 실패해, 팀원 한 명의 빌드만
깨지고 발견이 늦는다.

**사본을 읽는 스크립트에는 반드시 복사 훅을 함께 둔다.** 훅이 없으면 낡은 사본을
그대로 검사한다. 없는 필드를 참조해 실패하는 쪽은 원인을 찾기라도 쉽지만, 계약에서
필드를 지웠는데 낡은 사본에는 남아 있어 **통과해 버리는** 경우는 알아챌 방법이 없다.
`test` 같은 스크립트를 새로 추가할 때도 `pre` 훅을 같이 만든다.

응답 구조를 임의로 가정하지 않는다. 필요한 필드가 없으면 화면에서
만들어내지 말고 API 담당자에게 알린다.

### 개발 중 API 호출은 상대경로로 한다

`fetch('/api/balance?personaId=1')` 처럼 상대경로로 호출한다. Vite 개발 서버가
백엔드로 프록시하므로(`vite.config.ts`) CORS 설정 차이로 막히지 않는다.
배포 환경의 절대주소 주입 방식은 API 호출 계층을 만들 때 정한다(@fanfanduck).

### 금액 계산을 하지 않는다

할인액, 잔고, 실적 충족 여부는 모두 백엔드가 계산한 값을 표시만 한다.
프론트에서 재계산하면 백엔드와 값이 어긋난다.
`formatWon`, `formatManwon` 같은 표기 변환만 허용한다.

### 스타일은 contracts/ui-system.md 를 따른다

AI로 화면 코드를 생성할 때 이 파일을 반드시 함께 제공한다.

Tailwind 4 는 설정이 CSS 기반으로 바뀌어 `tailwind.config.js` 가 없다.
`ui-system.md` 의 클래스 문자열은 그대로 동작하므로 화면 코드는 영향받지 않지만,
AI가 만들어 준 `tailwind.config.js` 를 새로 추가하지 않는다. CSS 파일도
`src/index.css`(Tailwind import 한 줄) 외에는 만들지 않는다.

### explanation 이 null 이어도 결과를 표시한다

LLM 생성 실패 시 `explanation` 은 `null` 이지만 계산 결과는 정상이다.
설명이 없다고 카드 전체를 숨기지 않는다.

### 카테고리 선택지는 GET /api/categories 로 받는다

`spend_category` 코드는 DB 소유 값이라 화면이 지어내면 안 된다
(CLAUDE.md "No hardcoded enums that mirror DB data"). 코드를 자유 입력으로
받으면 이용자가 "온라인" 같은 그럴듯한 값을 쳤을 때 `INVALID_CATEGORY` 만
돌아온다 — 고를 수 있는 값을 알려주지 않고 틀렸다고만 답하는 셈이다.

`GET /api/categories` 가 `{ code, label }` 목록을 화면 표시 순서대로 내려준다.
`ALL` 은 규칙 매칭용 와일드카드라 이 목록에 없다. **한글 라벨도 서버가 주므로
`ONLINE → 온라인쇼핑` 대응표를 화면에 두지 않는다** — 두면 카테고리를 추가할 때
고쳐야 할 곳이 DB 와 프론트 두 군데가 되고, 한 곳을 빠뜨리면 조용히 어긋난다.

### isDemo 가 true 면 "시연용" 뱃지를 표시한다

`RouteCandidate.isDemo` 와 `NewCardSuggestion.isDemo` 는 그 카드가 실제 상품이
아니라 시연용 가상 상품이라는 뜻이다(`schema.sql` 의 `card.is_demo`).

지금 카탈로그의 카드 3종은 **전부 `true`** 다. 실제 할인액과 약관 인용이 붙은
추천에 아무 표시가 없으면 실존 상품으로 오해할 수 있어서, `ui-system.md` 와
`schema.sql` 컬럼 주석이 둘 다 화면 표시를 요구한다. 화면이 값을 지어낼 수
없으므로 계산 결과와 같은 경로로 실려 온다.

## 미결 사항

### 라우팅 방식

react-router 를 도입하지 않았다. 현재 `App.tsx` 는 화면 하나를 붙일 수 있는
껍데기뿐이다. 화면이 늘어나 라우팅이 필요해지면 **먼저 붙이는 사람이 임의로
정하지 말고 팀에 알린다.** 세 사람이 각자 담당 화면을 만들기 때문에 `App.tsx` 는
충돌이 나기 가장 쉬운 파일이다.

## 스택 선택 메모

- **TypeScript 는 5.9 로 고정했다.** 7 이 나와 있지만 `typescript-eslint` 의
  peer 범위가 `<6.1.0` 이라 린트를 붙이는 순간 설치가 막힌다.
- **ESLint 는 넣지 않았다.** 초기화 범위를 벗어나고, 위 제약 때문에 도입 시
  TypeScript 버전과 함께 정해야 한다. 필요해지면 그때 논의한다.
