# Seedance 2.5 examples

These authored examples demonstrate decisions, not measured generation quality. Explanations and deployment notes stay outside the model prompt.

## Simple scene

Brief: A red umbrella opens in the rain. Fixed camera, no dialogue or BGM.

```text
A single red umbrella slowly opens in the rain. The folded canopy spreads along its ribs, and raindrops fall from the edges. The camera holds a fixed close-up. Only the sound of rain and the umbrella opening is heard. No dialogue or background music.
```

## Korean dialogue and signage

Brief: 카페 사장이 들어오는 손님에게 "어서 오세요, 오늘은 라떼가 좋아요."라고 말한다. 카운터 위 간판에는 "오늘의 커피".

```text
Inside a small café in the morning, the owner behind the counter looks up as a customer walks in and says in Korean, "어서 오세요, 오늘은 라떼가 좋아요." A wooden sign above the counter reads "오늘의 커피". Medium shot at eye level with a slow push-in toward the owner. Ambient sound: an espresso machine hissing and a door chime.
```

Only the description is English. The spoken line and sign text stay in Korean because they must be heard and seen in Korean.

## Semantic keyframes

Brief: @Image1 is the starting state, @Image2 is the ending state. Both use reference_image. New 9:16 output; no dialogue.

```text
Use @Image1 as the first-frame reference and @Image2 as the last-frame reference. The subject moves continuously from the starting pose and object state in @Image1 to the ending state in @Image2, keeping the same identity and prop count. Adapt the composition while retaining the key spatial relationships. No dialogue.
```

Handoff: set 9:16 outside the prompt. Ordinary reference_image roles do not lock ratio or guarantee exact frame matches. Strict boundary roles would follow different settings.

## Audio edit with requested lip adaptation

Brief: Translate @Video1 dialogue into Korean; adapt lip movement; preserve everything else. No subtitles.

```text
Edit @Video1 as the sole source video. Translate its spoken dialogue into Korean, preserving the meaning, speaker assignments, and speaking intervals. Adapt only the speaking characters' lip movements to the translated lines. Preserve all other appearance, body actions, backgrounds, camera work, cuts, ambience, effects, and music. Do not add subtitles.
```

No unobserved transcript or replacement audio asset is invented.

## Extension before the source

Brief: Before @Video1 begins, the person approaches and takes the position in its opening frame.

```text
Extend @Video1 before its beginning. The same person approaches the opening-frame position and settles into its posture. End the new segment at the first-frame state of @Video1, maintaining the person's identity, prop positions, camera composition, lighting, motion continuity, and ambient sound. The person remains one continuous instance. Do not alter the original segment or introduce later source events early.
```
