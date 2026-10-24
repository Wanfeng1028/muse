import { readFileSync, readdirSync, lstatSync } from "node:fs";
import { join } from "node:path";
import { WorkProfileRegistry } from "./profile-registry.js";
import { WorkProfileSchema, type WorkProfile } from "./contracts.js";

const PROFILE_INPUTS = [
  {
    id: "workspace-default",
    title: "Creative workspace",
    description: "Discuss goals, inspect works, and create derived works.",
    capabilityIds: ["workspace", "adaptation", "translation", "visual"],
    artifactKinds: ["brief", "source", "export"],
  },
  {
    id: "longform-novel",
    title: "Long-form novel",
    capabilityIds: ["workspace", "longform", "adaptation", "visual"],
    requiredSkillIds: ["inkos-long-writing"],
    recommendedSkillIds: ["inkos-story-review"],
    artifactKinds: ["foundation", "chapter-plan", "chapter", "review", "cover"],
  },
  {
    id: "short-fiction",
    title: "Short fiction",
    capabilityIds: ["workspace", "short-fiction", "adaptation", "visual"],
    requiredSkillIds: ["inkos-short-writing"],
    artifactKinds: ["outline", "manuscript", "sales-package", "cover"],
  },
  {
    id: "script",
    title: "Script",
    capabilityIds: ["workspace", "script", "adaptation", "visual"],
    requiredSkillIds: ["inkos-script-writing"],
    artifactKinds: ["script-spec", "script"],
  },
  {
    id: "storyboard",
    title: "Storyboard",
    capabilityIds: ["workspace", "storyboard", "adaptation", "visual"],
    requiredSkillIds: ["inkos-storyboard"],
    artifactKinds: ["storyboard-spec", "storyboard", "image-prompt", "image"],
  },
  {
    id: "interactive-film",
    title: "Interactive film",
    capabilityIds: ["workspace", "interactive-film", "adaptation", "visual"],
    requiredSkillIds: ["inkos-interactive-film"],
    artifactKinds: ["story-graph", "flags", "script", "storyboard", "image"],
  },
  {
    id: "interactive-world",
    title: "Interactive world",
    capabilityIds: ["workspace", "interactive-world", "visual"],
    requiredSkillIds: ["inkos-play-world"],
    artifactKinds: ["world-contract", "world-state", "scene", "event", "image"],
  },
  {
    id: "translation",
    title: "Translation",
    capabilityIds: ["workspace", "translation"],
    requiredSkillIds: ["inkos-translation"],
    artifactKinds: ["source", "glossary", "translation", "review", "export"],
  },
  {
    id: "visual-asset",
    title: "Visual asset",
    capabilityIds: ["workspace", "visual"],
    requiredSkillIds: ["inkos-story-cover"],
    artifactKinds: ["image-prompt", "image"],
  },
] as const;

export function builtInWorkProfiles(): ReadonlyArray<WorkProfile> {
  return PROFILE_INPUTS.map((input) => WorkProfileSchema.parse({
    version: 2,
    ...input,
    description: "description" in input ? input.description : "",
    requiredSkillIds: "requiredSkillIds" in input ? input.requiredSkillIds : [],
    recommendedSkillIds: "recommendedSkillIds" in input ? input.recommendedSkillIds : [],
    contextRecipe: { id: input.id, sourceIds: ["task", "skills", "work"] },
    artifactSchemas: input.id === "short-fiction" ? { "source/final/short-story.json": "short-manuscript", "source/final/sales-package.json":"short-package" }
      : input.id === "translation" ? { "source/manifest.json": "translation-manifest", "source/glossary.json": "translation-glossary" } : {},
    qualityCriteria: [],
    production: {},
    confirmation: {
      inferredMutation: "execute",
      explicitRecoverableMutation: "execute",
      destructiveMutation: "confirm",
    },
  }));
}

export function createBuiltInWorkProfileRegistry(projectRoot?: string): WorkProfileRegistry {
  const registry = new WorkProfileRegistry();
  for (const profile of builtInWorkProfiles()) registry.register(profile);
  if (projectRoot) {
    const directory = join(projectRoot, ".inkos", "profiles");
    let files: string[] = [];
    try { files = readdirSync(directory); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    for (const file of files.filter(file => file.endsWith(".json")).sort()) {
      const path = join(directory, file);
      if (!lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) throw new Error("Profile must be a regular file");
      registry.replace(WorkProfileSchema.parse(JSON.parse(readFileSync(path, "utf8"))));
    }
  }
  return registry;
}
