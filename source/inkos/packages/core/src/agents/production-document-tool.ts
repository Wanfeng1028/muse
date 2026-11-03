import { Type } from "@sinclair/typebox";
import { StoryGraphContentToolSchema } from "../interactive-film/tool-schemas.js";

export const StoryboardPackageToolSchema = Type.Object({
  storyboard: Type.String({ minLength: 1, description: "Complete Markdown storyboard: shots, camera, action, sound, duration and continuity. Image prompts belong only in imagePrompts, not in this document." }),
  imagePrompts: Type.Array(
    Type.String({ minLength: 1, description: "One generation-ready image prompt for a storyboard shot." }),
    { minItems: 1, description: "The single image-prompt list, one prompt per shot in shot order." },
  ),
});

export const InteractiveFilmPackageToolSchema = Type.Object({
  storyTree: Type.String(),
  flags: Type.String(),
  script: Type.String(),
  storyboard: Type.String({ description: "Complete Markdown storyboard. Put the image-prompt list only in imagePrompts." }),
  imagePrompts: Type.Array(Type.String(), { description: "The single image-prompt list in shot order." }),
  storyGraph: StoryGraphContentToolSchema,
});
