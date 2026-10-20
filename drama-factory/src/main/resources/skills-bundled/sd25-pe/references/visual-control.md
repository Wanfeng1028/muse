# Keyframes, storyboards, and blockouts

Read [Task routing](task-routing.md) to distinguish strict API frame roles from semantic references. Prompt sentences do not set `content.role`.

## Frames

Name boundaries separately: `Use @Image1 as the first frame. Use @Image2 as the last frame.` These express intent; strict control requires corresponding interface roles. Ordinary reference images remain semantic anchors, with configurable ratio and approximate correspondence.

Describe continuous action between boundaries. Extra appearance/prop references must not overwrite their roles. For strict boundary frames, matching input ratios avoid stretching the last image; semantic keyframes do not automatically lock ratio.

For multiple keyframes, list order and each state. Intermediate states are not mandatory frozen holds or exact pixels. Do not collapse distinct frame roles into range assignments.

## Storyboards

State reading order, shot mapping, event, and missing information such as sound or inter-panel motion. Adopt intended composition/blocking; exclude annotations and placeholder appearance unless requested. A conceptual storyboard may need only a concise binding and story.

The source recommends fewer than 15 panels and clean line/stick-figure drawings with little text. This is a quality recommendation, not a hard input limit. Grids allow variation; separate keyframes provide stronger state ordering.

## Blockouts

State inherited dimensions and map geometric objects individually to final subjects. Coarse blockouts mainly supply paths, blocking, space, and camera; fine blockouts may also supply detailed structure. These are local writing categories, not API modes.

Describe the finished scene/materials/appearance/action consistently with the source. Inherit lighting changes or audio rhythm only when assigned. Exclude axes, controllers, guide lines, and gray materials when unintended. A blockout usually guides generation; an explicit edit still follows editing rules.
