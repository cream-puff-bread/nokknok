# public/fonts

로고 워드마크("넉넉") 전용 글꼴이다. 본문에는 쓰지 않는다.

## nokknok-wordmark.woff2

Pretendard v1.3.9 Bold 에서 `넉` 한 글자만 남긴 서브셋이다. 원본 791KB 가
428 바이트가 된다.

`index.html` 에서 CDN 으로 불러오지 않고 직접 두는 이유는, 심사위원이 URL 만
받아 둘러보는 경로에 우리가 통제하지 못하는 외부 요청을 늘리지 않기
위해서다(#38 리뷰). 같은 이유로 본문 글꼴은 시스템 폰트 그대로 둔다 —
전체 한글 글꼴을 받으면 서브셋이라도 수백 KB 다.

## 다시 만드는 법

글자가 바뀌면(`--text`) 다시 만든다. fonttools 는 이 저장소의 의존성이
아니다. 한 번 쓰고 마는 도구라 임시 위치에 설치한다.

```bash
pip install --target /tmp/ft fonttools brotli
curl -o /tmp/Pretendard-Bold.woff2 \
  https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/woff2/Pretendard-Bold.woff2
PYTHONPATH=/tmp/ft python -m fontTools.subset /tmp/Pretendard-Bold.woff2 \
  --text=넉 --flavor=woff2 --layout-features='' --no-hinting \
  --desubroutinize --name-IDs='' \
  --output-file=frontend/public/fonts/nokknok-wordmark.woff2
```

## 라이선스

Pretendard 는 SIL Open Font License 1.1 이다. 서브셋도 원본과 같은 조건이
적용되므로 `OFL.txt` 를 함께 둔다 — 지우지 않는다.
