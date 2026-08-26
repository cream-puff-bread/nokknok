# 배포

프론트와 백엔드를 다른 플랫폼에 올린다. 저장소는 하나지만 빌드는 서로 독립이다.

| 플랫폼 | 대상 | Root Directory | 정의 파일 |
|---|---|---|---|
| Render | 백엔드 (FastAPI) | `backend` | `render.yaml` |
| Vercel | 프론트 (Vite) | `frontend` | `frontend/vercel.json` |

## 프론트가 백엔드를 부르는 방법

**절대주소를 코드에 넣지 않는다.** 화면 코드는 개발이든 배포든 `/api/...` 상대경로로만 호출한다.

| 환경 | 경로 |
|---|---|
| 로컬 | Vite 개발 서버가 `localhost:8000` 으로 프록시 (`vite.config.ts`) |
| 배포 | Vercel rewrite 가 Render 로 전달 (`vercel.json`) |

이렇게 두면 얻는 것이 둘이다.

- **화면 코드가 두 환경에서 완전히 같다.** 빌드 시점에 주소를 주입할 필요가 없고, 주입을 빠뜨려 배포에서만 깨지는 경로가 생기지 않는다.
- **브라우저 CORS 가 아예 걸리지 않는다.** 요청이 Vercel 에서 서버 대 서버로 나가므로 프리플라이트가 없다. `CORS_ORIGIN` 설정이 어긋나 시연 중에 화면이 비는 상황을 원천적으로 없앤다.

백엔드 주소가 바뀌면 `vercel.json` 의 `destination` 한 곳만 고친다.

## 화면 주소를 새로고침해도 열리게 하는 것 (SPA 폴백)

라우팅은 브라우저에서 react-router 가 처리하지만, `/personas` 같은 주소로 **직접
들어오거나 새로고침하면 그 전에 서버가 먼저 응답해야 한다.** Vercel 은 그런 경로에
해당하는 파일이 없으므로 404 를 낸다 — 라우터가 실행될 기회조차 없다.

그래서 남은 경로를 전부 `index.html` 로 보낸다.

```json
"rewrites": [
  { "source": "/api/:path*", "destination": "https://nokknok-api.onrender.com/api/:path*" },
  { "source": "/(.*)",       "destination": "/index.html" }
]
```

**순서가 중요하다.** `/api` 규칙이 먼저 와야 API 요청이 `index.html` 로 삼켜지지
않는다. 정적 자산(`/assets/*.js`, `/favicon.ico`)은 Vercel 이 rewrites 보다
파일시스템을 먼저 확인하므로 영향받지 않는다.

이 설정이 없으면 **라우터를 도입한 이유가 통째로 사라진다.** 새로고침도, 딥링크도,
뒤로가기 후 새로고침도 전부 404 가 된다. 콜드스타트가 30초 넘게 걸리는 동안
심사위원이 새로고침하면 정확히 그 화면을 보게 된다.

## 빌드 감시 경로

한쪽만 고쳐도 양쪽이 재배포되면 빌드 시간이 낭비되고 재배포 중 서비스가 잠시 끊긴다.

**Vercel** — `vercel.json` 의 `ignoreCommand`

```bash
git diff --quiet HEAD^ HEAD -- . ../contracts
```

Vercel 은 Root Directory(`frontend`)에서 명령을 실행하므로 경로가 `frontend/` 가 아니라 `.` 이다. `../contracts` 를 함께 보는 이유는 **`contracts/types.ts` 가 프론트 빌드의 입력**이기 때문이다. `prebuild` 가 그 파일을 `src/types/contract.ts` 로 복사하므로, 계약만 바뀐 커밋에서도 프론트를 다시 빌드해야 화면이 새 타입을 반영한다.

**Render** — `render.yaml` 의 `buildFilter.paths` 에 `backend/**`. 백엔드는 런타임에 `contracts/` 를 읽지 않는다(정합성 검사는 테스트에서만 한다).

## 대시보드에서만 되는 설정

파일로 못 박을 수 없는 항목이다. 인스턴스를 새로 만들면 다시 해야 한다.

### Render

| 항목 | 값 |
|---|---|
| Root Directory | `backend` |
| Health Check Path | `/api/health` |
| 비밀 환경변수 | `DATABASE_URL` · `LLM_API_KEY` · `LLM_MODEL` · `CORS_ORIGIN` |

`DATABASE_URL` 은 **반드시 풀링(`-pooler`) 주소**를 쓴다. Direct 주소는 무료 티어 동시 연결 한도를 금방 넘긴다.

### Vercel

| 항목 | 값 |
|---|---|
| Root Directory | `frontend` |
| Framework Preset | Vite |

환경변수는 없다. 백엔드 주소는 `vercel.json` 의 rewrite 에 있다.

### GitHub

`.github/workflows/keep-alive.yml` 이 쓰는 저장소 시크릿을 등록한다.

| 시크릿 | 값 |
|---|---|
| `API_HEALTH_URL` | `https://<render-서비스명>.onrender.com/api/health` |

Render 무료 인스턴스는 15분 무응답이면 슬립되고 재기동에 30~60초가 걸린다. 심사 기간에 URL 접근 불가는 결격 사유라 10분마다 깨워둔다. **시크릿을 등록하지 않으면 워크플로가 조용히 실패한다** — 실패해도 파이프라인을 막지 않도록 짜여 있어 알림이 오지 않는다.

## 배포 후 확인

순서대로 확인한다. 앞 단계가 안 되면 뒤는 볼 필요가 없다.

```bash
# 1. 백엔드가 살아 있는가
curl -s https://<render>.onrender.com/api/health
# → {"status":"ok","time":"..."}

# 2. DB에 붙는가 (health 는 DB를 안 보므로 따로 확인해야 한다)
curl -s https://<render>.onrender.com/api/personas | head -c 200
# → 페르소나 3건

# 3. API 문서가 노출되는가
curl -s -o /dev/null -w "%{http_code}\n" https://<render>.onrender.com/docs

# 4. 프론트에서 rewrite 가 도는가 (같은 오리진으로 나가야 한다)
curl -s https://<vercel>.vercel.app/api/health
# → {"status":"ok","time":"..."}

# 5. 화면 주소를 직접 열어도 되는가 (SPA 폴백)
curl -s -o /dev/null -w "%{http_code}
" https://<vercel>.vercel.app/personas
# → 200 (404 면 폴백 규칙이 빠진 것)

# 6. 정적 자산이 폴백에 삼켜지지 않았는가
curl -s -o /dev/null -w "%{http_code}
" https://<vercel>.vercel.app/favicon.ico
```

4번이 핵심이다. 1번이 되는데 4번이 안 되면 `vercel.json` 의 rewrite 주소가 틀린 것이다.

5번은 라우팅을 도입한 뒤부터 의미가 생긴다. 여기서 404 가 나오면 새로고침과
딥링크가 전부 깨지므로, 라우터를 넣기 전에 먼저 확인해야 한다.

## 콜드스타트

`CONTRIBUTING.md` 의 시연 안정성 항목대로, **시연 전에 10분 이상 방치했다가 접속해 본다.** keep-alive 가 돌고 있어도 워크플로가 밀리거나 GitHub Actions 가 지연되면 슬립에 들어간다.

첫 요청이 30~60초 걸리는 상황에서 화면이 어떻게 보이는지 확인한다. 로딩 표시가 없으면 멈춘 것처럼 보인다.
