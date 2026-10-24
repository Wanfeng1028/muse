import { describe, expect, it } from "vitest";
import { runResearchReport } from "../agents/researcher.js";

describe("ResearcherAgent", () => {
  it("builds a traceable research report without mutating story state", async () => {
    const report = await runResearchReport(
      {
        topic: "宋代县衙巡检职责",
        purpose: "worldbuilding",
        depth: "quick",
      },
      {
        search: async (query, maxResults) => {
          expect(query).toContain("宋代县衙巡检职责");
          expect(maxResults).toBeGreaterThan(0);
          return [
            {
              title: "宋代地方治安资料",
              url: "https://example.com/song-policing",
              snippet: "巡检负责地方治安、缉捕盗贼，并与县衙形成协作关系。",
            },
          ];
        },
        fetch: async (url) => {
          expect(url).toBe("https://example.com/song-policing");
          return "巡检司常设于要冲，职责包括巡逻、缉盗、盘查交通要道。";
        },
      },
    );

    expect({
      sourceIds: report.sources.map((source) => source.id),
      sourceUrls: report.sources.map((source) => source.url),
      queries: report.queryLog,
      failures: report.partialFailures,
    }).toEqual({
      sourceIds: ["S1"],
      sourceUrls: ["https://example.com/song-policing"],
      queries: ["宋代县衙巡检职责"],
      failures: [],
    });
  });
});
