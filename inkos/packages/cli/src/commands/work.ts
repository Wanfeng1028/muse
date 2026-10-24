import { Command } from "commander";
import {
  CreativeEpisodeStore,
  listWorkManifests,
  loadWorkManifest,
  migrateLegacyWorks,
} from "@actalk/inkos-core";
import { join } from "node:path";
import { findProjectRoot, log, logError } from "../utils.js";

export const workCommand = new Command("work")
  .description("Inspect creative Works, artifacts, revisions, and Episodes");

workCommand.command("migrate")
  .description("Preview or copy legacy projects into the Work library")
  .option("--apply", "Apply the migration, retaining original directories")
  .option("--source <path>", "Migrate one legacy directory, for example books/my-book")
  .option("--json", "Output JSON")
  .action(async (opts: { apply?: boolean; source?: string; json?: boolean }) => {
    try {
      const results = await migrateLegacyWorks(findProjectRoot(), opts);
      if (opts.json) log(JSON.stringify({ applied: opts.apply === true, results }, null, 2));
      else for (const item of results) log(`${item.source} | ${item.status} | ${item.fileCount ?? 0} files${item.error ? ` | ${item.error}` : ""}`);
      if (results.some((item) => item.status === "invalid" || item.status === "conflict")) process.exitCode = 1;
    } catch (error) { logError(String(error)); process.exitCode = 1; }
  });

workCommand
  .command("list")
  .description("List every creative Work across all content types")
  .option("--profile <profileId>", "Filter by Work profile")
  .option("--json", "Output JSON")
  .action(async (opts: { profile?: string; json?: boolean }) => {
    try {
      const root = findProjectRoot();
      const works = await listWorkManifests(root, opts.profile?.trim() || undefined);
      const output = works.map((work) => ({
        id: work.id,
        title: work.title,
        profileId: work.profileId,
        language: work.language,
        status: work.status,
        artifacts: work.artifacts.length,
        updatedAt: work.updatedAt,
      }));
      if (opts.json) {
        log(JSON.stringify({ works: output }, null, 2));
        return;
      }
      if (output.length === 0) {
        log("No creative Works found.");
        return;
      }
      for (const work of output) {
        log(`${work.id} | ${work.profileId} | ${work.title} | ${work.artifacts} artifacts | ${work.status}`);
      }
    } catch (error) {
      if (opts.json) log(JSON.stringify({ error: String(error) }));
      else logError(`Failed to list Works: ${error}`);
      process.exitCode = 1;
    }
  });

workCommand
  .command("show")
  .description("Show one Work with artifact revisions and recent Episodes")
  .argument("<work-id>", "Work ID")
  .option("--json", "Output JSON")
  .action(async (workId: string, opts: { json?: boolean }) => {
    let episodes: CreativeEpisodeStore | undefined;
    try {
      const root = findProjectRoot();
      const work = await loadWorkManifest(root, workId);
      episodes = new CreativeEpisodeStore(join(root, ".inkos", "harness.sqlite"));
      const recentEpisodes = episodes.listEpisodes({ workId, limit: 50 });
      if (opts.json) {
        log(JSON.stringify({ work, episodes: recentEpisodes }, null, 2));
        return;
      }
      log(`${work.title} (${work.id})`);
      log(`Profile: ${work.profileId} | Language: ${work.language} | Status: ${work.status}`);
      log(`Artifacts: ${work.artifacts.length} | Episodes: ${recentEpisodes.length}`);
      for (const artifact of work.artifacts) {
        const current = artifact.revisions.find((revision) => revision.id === artifact.currentRevisionId);
        log(`  ${artifact.kind} | ${current?.path ?? "(no accepted revision)"} | ${artifact.revisions.length} revision(s)`);
      }
      for (const episode of recentEpisodes.slice(0, 10)) {
        log(`  episode ${episode.id} | ${episode.status} | ${episode.startedAt}`);
      }
    } catch (error) {
      if (opts.json) log(JSON.stringify({ error: String(error) }));
      else logError(`Failed to inspect Work: ${error}`);
      process.exitCode = 1;
    } finally {
      episodes?.close();
    }
  });
