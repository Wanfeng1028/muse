# H3 examples

These are authored format examples, not observed generation results. Their scene details are not defaults for unrelated requests.

## T2VA, complete silence

Brief: A paper boat drifts across a puddle. Fixed camera. No sound or music.

```text
integrated_multimodal_description: [Shot 1] Live-action close-up of a single folded paper boat drifting slowly across a shallow puddle. Small ripples gently turn its bow before it settles beside a wet stone. The camera holds a static shot.

overall_soundscape: N/A

non_diegetic_music: N/A
```

## FL2VA, eight seconds

Brief: Picture 1 is a closed umbrella; Picture 2 is the same umbrella open. One continuous eight-second shot, rain sounds, no music.

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 8.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Begin with the subject, umbrella, and framing in Picture 1. The subject raises the umbrella and pushes its runner upward; the ribs spread and the canopy opens continuously. The subject settles into the pose and composition in Picture 2 at the end of the shot.

overall_soundscape: Rain taps the ground and then the opening canopy. The runner clicks into place.

non_diegetic_music: N/A
```

## Ref2VA, voice reference with a separate speaker ID

Brief: Use Picture 1 for the character's appearance and Audio 1 only for voice timbre. The character says “안녕하세요.” at a doorway. No music. These roles are given in text; no appearance or transcript is inferred.

```text
subject_definitions:
<Subject 1> is the character whose appearance comes from <Picture 1>.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary: [reference generation + audio reference] <Subject 1> greets the viewer at a doorway, using the voice timbre of <Audio 1> without copying its dialogue.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the referenced character appearance is retained.
<Audio 1>: reference - only voice timbre is used; the target words come from the brief.

detailed_description: Natural live-action style with soft daylight.
[Shot 1] A medium shot frames <Subject 1> at a doorway. <Subject 1> (S1) looks toward the viewer and says in the voice timbre referenced from <Audio 1>, <d>[Korean] 안녕하세요.</d> The camera holds still as the character finishes the greeting.

overall_soundscape: Soft room tone continues beneath the greeting.

non_diegetic_music: N/A
```

Picture 1 is source provenance inside the subject definition, not an independently tracked frame anchor. Its own retention entry is therefore unnecessary. The audio label and speaker ID have different roles.
