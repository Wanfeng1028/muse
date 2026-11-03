# 이미지 프롬프트 블록

고정 블록(STYLE, 캐릭터, CUT)을 변수로 두고, 장면마다 동작만 바꿔 조립한다. 모든 컷에서 조명, 시간대, 렌즈, 색감을 같게 유지하는 것이 연속성의 핵심이다. 여러 장은 동시에 생성한다. 모든 블록 끝에 글자·로고 금지 문구를 붙이고, 필요한 글자는 코드로 올린다. 중괄호 {}는 프로젝트에 맞게 채운다.

## 광택 3D 오브젝트 (투명 배경, 검증)

어두운 무대 위 광고 룩의 주인공이다. 첫 물체 하나를 만든 뒤, 그 물체를 참조 이미지로 넣어 나머지를 같은 재질과 조명으로 만든다. 이벤트나 기능마다 상징 물체 하나를 정한다(예: 촬영 → 즉석카메라, 방 탈출 → 자물쇠, 보물찾기 → 보물상자, 퀴즈 → 황금 종).

```
{one object, e.g. A cute retro instant photo camera, glossy hot pink and white body, big shiny lens, a blank white photo sliding out}, slight three-quarter view. Premium glossy 3D toy-like render in the exact same material and lighting style as the referenced object: smooth rounded shapes, soft studio lighting, bright specular highlights, subtle rim light, rich saturated color, clean edges. Single object, centered, fully visible, isolated on a transparent background. No text, no letters, no numbers, no logos, no watermark.
```

- 투명 배경 옵션을 켜고 생성한 뒤, 알파 채널의 경계 상자로 잘라 저장한다. 흐린 사본(가우시안 14px 안팎)을 따로 만들어 배경의 먼 층에 쓴다.
- 한 장면에 물체는 하나. 두 물체를 한 이미지에 넣어야 하면(O와 X처럼) "side by side with a wide empty gap"을 넣는다.
- 스타일프레임은 같은 블록에 무대를 붙여 만든다: `... on a dark glossy stage, deep navy background, neon rim light, soft bokeh, cinematic lighting, wide 16:9`.

## 미니어처 실사 (피규어)

STYLE:
```
Hyperrealistic macro photograph of a miniature diorama on {a real wooden desk in a place related to the product} at {time of day}, warm golden light from windows behind (strong backlight from upper right), volumetric light rays, floating dust particles, 100mm macro lens f/2.8, shallow depth of field, cinematic teal-orange color grade, subtle film grain, photorealistic, vertical 4:5 composition. No readable text, no letters, no logos, no watermark.
```
캐릭터 (참조 이미지와 함께):
```
the small collectible vinyl figure of the referenced character ({same face, hair, outfit described in one fixed sentence}, glossy toy-like skin, chibi proportions)
```
포즈 컷 (투명 배경. 고정 배경 위에 바꿔 끼우는 스톱모션용):
```
Full-body product photo of {character}. Pose: {pose}. Warm golden rim light from upper right, soft warm fill, photorealistic toy photography, entire figure visible including shoes, isolated on transparent background.
```

## 웹툰·만화

```
Style: high-energy Korean webtoon / Japanese shonen manga comic panel, bold clean black ink outlines, dramatic cel shading with halftone screentone dots, dynamic speed lines, vibrant limited palette of {brand color 1 hex}, {brand color 2 hex}, cream white and deep black, strong contrast, cinematic dramatic angle, comic book print texture. Vertical 4:5 composition, full-bleed single panel, no panel borders, no speech bubbles, no text, no letters, no sound-effect lettering, no logos, no watermark.
```
주인공 설명은 한 문장으로 고정해 모든 컷에 붙인다. 첫 컷은 이후 컷의 참조 이미지로 쓴다. 제품에 원래 있는 캐릭터(표지 로봇 등)는 참조 이미지로 넣고, `exactly like the referenced {character}: ...`처럼 외형을 다시 적는다.

## 실사 사진

```
Ultra-photorealistic professional photograph, natural light, realistic materials and textures, true-to-life colors, high dynamic range, subtle film grain, vertical 4:5 composition. Not an illustration, not CGI, not anime. No text, no readable letters, no logos, no watermark.
```

## 통과할 입구 표시 (크로마키)

```
IMPORTANT: {the empty open gap of that one open window} is filled with perfectly flat, uniform, pure chroma-key green (#00FF00) — no texture, no reflection, no glare, nothing drawn in it. The green area is about {22}% of the image width.
```
입구는 공간 안에 자연스럽게 있는 것으로 고른다. 바람에 커튼이 날리는 열린 창이나 열린 문처럼. 화면 중앙의 네모 화면을 반복하지 않는다.

## 깊이 지도 (원본 사진을 참조 이미지로)

```
Convert this exact photograph into its monocular depth map. Output a smooth grayscale depth image only: pure white = the surfaces nearest to the camera, pure black = the farthest surfaces, smooth continuous gradients along floors, walls and ceilings and crisp edges at object boundaries. Preserve the exact composition, framing, perspective, object positions and outlines pixel-for-pixel so it overlays the original perfectly. No colors, no textures, no text, no lighting shading — only distance.
```

## 같은 장면의 전후 편집

```
Edit this exact photograph. Keep the identical camera position, lens, framing, perspective, layout, furniture and lighting exactly the same. Change only one thing: {change}. Ultra-photorealistic photograph, no text, no people.
```

## 흩날리는 소품 (투명 배경)

```
A single real {object, e.g. sheet of office paper}, slightly curved in the air as if flying, {generic blurred unreadable content}, realistic texture, warm golden light. Isolated on a transparent background. Photorealistic, no readable text, no logos.
```
