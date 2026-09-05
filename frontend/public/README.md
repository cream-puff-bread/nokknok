# public

정적 파일. Vite 가 빌드 산출물 루트로 그대로 복사한다.

## 로고 이미지

`logo-mark.png`(헤더·진입 연출), `favicon-32.png`(탭 아이콘),
`apple-touch-icon.png`(iOS 홈 화면)는 모두 **같은 원본 한 장**에서 나왔다.
원본은 2000x2000, 654KB 라 그대로 쓰지 않는다.

원본이 바뀌면 셋을 다시 만든다. 여백을 잘라 내고 정사각으로 맞추는 단계를
빼먹으면, 줄였을 때 마크가 가운데 조그맣게 박힌다.

```python
from PIL import Image

im = Image.open('logo.png').convert('RGBA')
im = im.crop(im.getbbox())          # 투명 여백 제거

w, h = im.size                       # 정사각으로 맞추기
side = max(w, h)
square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
square.paste(im, ((side - w) // 2, (side - h) // 2))

for size, name in [(256, 'logo-mark.png'), (32, 'favicon-32.png'), (180, 'apple-touch-icon.png')]:
    square.resize((size, size), Image.LANCZOS).save('public/' + name, optimize=True)
```

SVG 파비콘은 두지 않는다. 원본이 래스터라 만들 수 없고, 억지로 흉내 내면
로고와 다른 그림이 된다.

## fonts/

로고 워드마크 전용 글꼴. `fonts/README.md` 참고.
