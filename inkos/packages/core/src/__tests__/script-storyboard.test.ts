import { describe, expect, it } from "vitest";
import {
  renderInteractiveFilmSpec,
  renderScriptSpec,
  renderStoryboardSpec,
} from "../agents/script-storyboard.js";
import { createStoryboardAssetsManifest } from "../pipeline/script-storyboard-runner.js";

describe("script and storyboard host contracts", () => {
  it("preserves confirmed requirements in human-readable creation specs", () => {
    expect(renderScriptSpec({
      title: "冷库账页",
      targetFormat: "vertical_short_drama",
      requirements: "调查线七成，家怨三成。",
      episodeCount: 12,
    })).toContain("调查线七成，家怨三成");
    expect(renderStoryboardSpec({
      title: "冷库账页",
      visualStyle: "写实冷色",
      aspectRatio: "9:16",
      requirements: "每镜头都要有关键道具。",
    })).toContain("每镜头都要有关键道具");
    expect(renderInteractiveFilmSpec({
      title: "盛世账页",
      requirements: "多结局，变量记录玩家每次关键抉择。",
      budget: "5000元",
    })).toContain("多结局");
  });

  it("builds image assets directly from typed prompts", () => {
    const manifest = createStoryboardAssetsManifest({
      title: "冷库账页",
      projectId: "cold-ledger",
      baseDir: "works/cold-ledger/source",
      storyboardPath: "works/cold-ledger/source/storyboard.md",
      imagePromptsPath: "works/cold-ledger/source/image-prompts.md",
      imagePrompts: ["冷库门口，女出纳推门，冷色写实，9:16", "旧账页特写，手电光扫过红章"],
      createdAt: "2026-06-16T00:00:00.000Z",
    });
    expect(manifest.assets.map((asset) => asset.prompt)).toEqual([
      "冷库门口，女出纳推门，冷色写实，9:16",
      "旧账页特写，手电光扫过红章",
    ]);
  });
});
