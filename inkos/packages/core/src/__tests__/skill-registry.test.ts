import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { appendActivatedSkillGuidance } from "../agents/base.js";
import { createBuiltInWorkProfileRegistry } from "../harness/builtin-profiles.js";
import { createSkillRegistry, loadAvailableAgentSkills } from "../skills/index.js";
import {
  applyRequiredProfileSkills,
  applyRequiredWorkSkills,
  resolveProfileSkillActivations,
} from "../skills/activations.js";
import { WorkProfileSchema } from "../harness/contracts.js";
import { createWorkManifest } from "../harness/work-store.js";

const externalSkill = {
  id: "writer-distillation",
  name: "Writer Distillation",
  description: "Distill transferable writing craft.",
  body: "Separate craft from surface wording.",
  source: "external",
} as const;

describe("AgentSkills registry", () => {
  it("does not inject implicit InkOS built-in skills", () => {
    const registry = createSkillRegistry();

    expect(registry.listSkills()).toEqual([]);
  });

  it("resolves user-forced skills", () => {
    const registry = createSkillRegistry({ skills: [externalSkill] });

    const result = registry.resolveSkills({
      requestedSkills: ["writer-distillation"],
    });

    expect(result.usedSkills.map((skill) => skill.id)).toEqual(["writer-distillation"]);
    expect(result.forcedSkillIds).toEqual(["writer-distillation"]);
    expect(result.missingSkillIds).toEqual([]);
  });

  it("reports unknown forced skills instead of silently dropping them", () => {
    const registry = createSkillRegistry({ skills: [externalSkill] });

    const result = registry.resolveSkills({
      requestedSkills: ["not-a-skill", "writer-distillation"],
    });

    expect(result.usedSkills.map((skill) => skill.id)).toEqual(["writer-distillation"]);
    expect(result.missingSkillIds).toEqual(["not-a-skill"]);
  });

  it("excludes disabled skills from forced selection", () => {
    const registry = createSkillRegistry({ skills: [externalSkill] });

    const result = registry.resolveSkills({
      disabledSkills: ["writer-distillation"],
      requestedSkills: ["writer-distillation"],
    });

    expect(result.usedSkills).toEqual([]);
    expect(result.disabledSkillIds).toEqual(["writer-distillation"]);
  });

  it("does not auto-load skills without an explicit request", () => {
    const registry = createSkillRegistry();

    expect(registry.resolveSkills({}).usedSkills.map((skill) => skill.id)).toEqual([]);
  });

  it("applies required profile Skills to the main turn alongside user-forced Skills", () => {
    const scriptSkill = {
      id: "inkos-script-writing",
      name: "Script Writing",
      description: "Script craft.",
      body: "Write performable scenes.",
      source: "builtin" as const,
    };
    const registry = createSkillRegistry({ skills: [scriptSkill, externalSkill] });
    const profile = createBuiltInWorkProfileRegistry().require("script");
    const effective = applyRequiredProfileSkills(
      registry.resolveSkills({ requestedSkills: ["writer-distillation"] }),
      profile,
    );

    expect(effective.usedSkills.map((skill) => skill.id)).toEqual([
      "inkos-script-writing",
      "writer-distillation",
    ]);
    expect(effective.forcedSkillIds).toEqual([
      "inkos-script-writing",
      "writer-distillation",
    ]);
    expect(createBuiltInWorkProfileRegistry().require("visual-asset").requiredSkillIds)
      .toEqual(["inkos-story-cover"]);
  });

  it("keeps a derived Work's professional Skill active after its creation turn", () => {
    const skills = [
      {
        id: "inkos-long-writing",
        name: "Long Writing",
        description: "Long-form craft.",
        body: "Preserve long-form continuity.",
        source: "builtin" as const,
      },
      {
        id: "inkos-fanfic-writing",
        name: "Fanfic Writing",
        description: "Fan-fiction craft.",
        body: "Preserve source canon and the allowed divergence.",
        source: "builtin" as const,
      },
    ];
    const registry = createSkillRegistry({ skills });
    const work = createWorkManifest({
      id: "fanfic-work",
      title: "Fanfic Work",
      profileId: "longform-novel",
      language: "en",
      metadata: { creationKind: "fanfic" },
    });
    const effective = applyRequiredWorkSkills(
      applyRequiredProfileSkills(
        registry.resolveSkills({}),
        createBuiltInWorkProfileRegistry().require("longform-novel"),
      ),
      work,
    );

    expect(effective.usedSkills.map((skill) => skill.id)).toEqual([
      "inkos-long-writing",
      "inkos-fanfic-writing",
    ]);
    expect(effective.forcedSkillIds).toEqual([
      "inkos-long-writing",
      "inkos-fanfic-writing",
    ]);
  });

  it("fails loudly when a required professional skill is unavailable", () => {
    const profile = WorkProfileSchema.parse({
      version: 2,
      id: "script",
      title: "Script",
      description: "Script creation",
      capabilityIds: ["script"],
      requiredSkillIds: ["inkos-script-writing"],
      recommendedSkillIds: [],
      artifactKinds: ["script"],
      confirmation: {
        inferredMutation: "execute",
        explicitRecoverableMutation: "execute",
        destructiveMutation: "confirm",
      },
    });

    expect(() => resolveProfileSkillActivations([], profile)).toThrow(
      'Profile "script" requires unavailable skill(s): inkos-script-writing',
    );
  });

  it("loads a project Skill override through the Work Profile into worker guidance", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-skill-flow-"));
    try {
      const skillDir = join(root, ".agents", "skills", "inkos-long-writing");
      await mkdir(skillDir, { recursive: true });
      await writeFile(join(skillDir, "SKILL.md"), [
        "---",
        "name: inkos-long-writing",
        "description: Project long-form method.",
        "---",
        "PROJECT_LONGFORM_METHOD",
      ].join("\n"));

      const loaded = await loadAvailableAgentSkills({ projectRoot: root });
      const registry = createSkillRegistry({ skills: loaded.skills });
      const activations = resolveProfileSkillActivations(
        registry.listSkills(),
        createBuiltInWorkProfileRegistry().require("longform-novel"),
      );
      const messages = appendActivatedSkillGuidance(
        [{ role: "system", content: "worker protocol" }],
        activations,
      );

      expect(activations.map((item) => [item.skill.id, item.skill.source])).toEqual([
        ["inkos-long-writing", "project"],
      ]);
      expect(messages[0]?.content).toContain("PROJECT_LONGFORM_METHOD");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
