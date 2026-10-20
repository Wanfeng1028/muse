# split-screen-workbench · 左右分屏工作台 (split-screen-workbench, 镜18)

The frame splits down the middle: the presenter (matted onto yellow paper) on the left as "你 创意+拍摄" (you: creative + shooting), an automated editing workbench on the right as "Agent 剪辑+包装" (Agent: editing + packaging).

## Source
`../_shared/video20-a2-shots/src/shot18.py`, class `Shot18`.

## How it works
The two halves push in from a closed centre seam over 15 frames (and push back together to close). The left half shows the presenter matted out of his live footage (premultiplied alpha) composited onto yellow paper with a role card. The right half is a mocked-up editing workbench: the real vlog demo clip plays in a preview pane above a timeline that performs a ripple-cut removing a dead-air segment in sync with the real jump cut in the source footage, an audio waveform lane fills up to a moving playhead, and three small chips ("+转场"/"+音效"/"+贴纸字幕") pop in one after another, each growing its own effect block on the timeline as it lands. Both role cards (你/Agent) swap to their "+ 拍摄"/"+ 包装" second-half wording partway through, on their respective words.

## Notes
Like `fullscreen-dialog`, this file's docstring says "same components as storyboard shot18 (render_v2 workbench / role_card / scissors)" — verified to be a design-lineage note only: `shot18.py` defines its own local `pill`/`role_card`/`scissors`, and doesn't call `render_v2.py`'s `workbench` at all (that name only appears in this file's comments, never as a function call). See `../_shared/video20-a2-shots/src/README.md` for the full explanation.
