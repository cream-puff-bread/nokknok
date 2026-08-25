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
```

4번이 핵심이다. 1번이 되는데 4번이 안 되면 `vercel.json` 의 rewrite 주소가 틀린 것이다.

## 콜드스타트

`CONTRIBUTING.md` 의 시연 안정성 항목대로, **시연 전에 10분 이상 방치했다가 접속해 본다.** keep-alive 가 돌고 있어도 워크플로가 밀리거나 GitHub Actions 가 지연되면 슬립에 들어간다.

첫 요청이 30~60초 걸리는 상황에서 화면이 어떻게 보이는지 확인한다. 로딩 표시가 없으면 멈춘 것처럼 보인다.
