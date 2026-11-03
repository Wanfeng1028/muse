# Wan 3.0 prompt transformations

Read this file only when an example helps resolve structure or output style. Examples illustrate decisions; do not copy their subjects or details into unrelated prompts.

## Rough T2V concept

**Input:** `비 오는 밤, 편의점 앞에서 우산을 접고 들어가는 남자. 쓸쓸한 느낌.`

**Output:**

```text
Cinematic realism, night exterior in steady rain. A tired man in a dark office coat approaches a small neighborhood convenience store, pauses beneath the fluorescent awning, shakes the rain from his umbrella once, folds it, and steps through the glass door as warm interior light spills across the wet pavement. Medium-wide eye-level shot with a slow lateral tracking move, cool blue street tones contrasted with the warm store light, soft reflections and low saturation. Raindrops ripple through puddles while distant traffic passes as blurred light.
```

Why it works: one continuous action, a compatible camera move, and visual choices that express loneliness without relying on abstract literary language.

## I2V animation

**Input:** A portrait image plus `머리카락이 바람에 날리고 카메라가 가까워졌으면 좋겠어.`

**Output:**

```text
A gentle breeze lifts and separates a few strands of the subject's hair, then the motion spreads naturally through the rest of the hair and the edge of the clothing. The subject blinks once and shifts their gaze slightly toward the lens while keeping the same identity, pose, wardrobe, background, and lighting. The camera slowly pushes in from the existing framing, with stable facial features and no new objects.
```

Why it works: it animates the supplied frame rather than rebuilding it and names what must remain stable.

## Product motion

**Input:** `검은 향수병이 고급스럽게 회전하고 빛이 지나가는 광고 영상.`

**Output:**

```text
Luxury product-film style. A single glossy black perfume bottle stands on a dark reflective pedestal against a seamless charcoal background. The bottle rotates slowly clockwise through a quarter turn as a narrow white highlight travels cleanly across the glass, revealing the curved silhouette and cap edges before fading into shadow. Fixed camera, centered close-up, long-focus lens, hard rim light with controlled specular reflections, high contrast, deep neutral tones. The bottle remains sharply defined throughout the movement.
```

Why it works: exact object motion and light behavior are prioritized; the fixed camera prevents competing movement.

## Two speakers with sound

**Input:** `카페에서 형사와 바리스타가 짧게 대화. 형사는 낮은 목소리로 “어젯밤 그 사람을 봤습니까?” 바리스타가 머뭇거리며 “아니요.”`

**Output:**

```text
Cinematic realism, quiet café before opening, soft gray daylight through the front window. [Detective: tall man in a charcoal coat] places a photograph on the counter and leans forward slightly. In a low, controlled Korean voice he asks, "어젯밤 그 사람을 봤습니까?" After a brief pause, [Barista: woman in a beige apron] stops wiping a cup, glances toward the back room, and answers hesitantly in a soft Korean voice, "아니요." Medium two-shot at eye level with a fixed camera, restrained cool tones. Ambient sound: refrigerator hum, a ceramic cup touching wood, faint traffic outside.
```

Why it works: unique speaker labels, action anchors, distinct voices, and explicit timing reduce dialogue attribution errors.

## Wan 3.0 multi-shot reference narrative

**Input:** `Image 1의 로봇이 Image 2의 작업실에서 종이비행기를 접어 날린다. 6초, 2개 샷. 대사와 음악 없음.`

```text
A two-shot story of the robot in Image 1 folding and launching a paper airplane in the workshop in Image 2. Preserve the same robot, workshop, and single paper airplane across both shots.
Shot 1 [0–3 s]: A medium shot shows the robot completing the final fold of the paper airplane at the workbench.
Shot 2 [3–6 s]: Cut to a side view as the robot lifts the same airplane and gently launches it across the workshop. The camera follows its short glide.
Sound effects: paper creases and a light rustle during the launch. No dialogue. No background music.
```

This uses Wan 3.0's multi-shot formula and separate image numbering. It does not turn two shots into two required generation jobs or treat omitted dialogue/music as silence. It is an authored example, not a generated-video test.
