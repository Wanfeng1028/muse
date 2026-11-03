import { z } from "zod";
import { numberSourceLines, sourceLineBodies } from "../utils/source-text.js";

export const ObservationSchema = z.object({
  code: z.string().min(1),
  summary: z.string().min(1),
  evidence: z.array(z.string()).default([]),
  category: z.enum(["execution", "quality", "scope"]).optional(),
  assessment: z.enum(["issue", "resolved", "unavailable", "observation"]).optional(),
  scope: z.string().optional(),
  targetHash: z.string().optional(),
  target: z.object({ workId: z.string(), artifactId: z.string(), revisionId: z.string() }).strict().optional(),
  sourceRefs: z.array(z.object({ sourceId: z.string().min(1), quote: z.string().min(1) }).strict()).optional(),
}).strict();

export type Observation = z.infer<typeof ObservationSchema>;

/** Number display lines without modifying the authoritative source text. */
export function numberReviewSource(source: string): string {
  return numberSourceLines(source);
}

type ReviewSourceSubmission = Omit<Observation,"sourceRefs"> & {
  sourceRefs?: ReadonlyArray<{sourceId:string;quote?:string;startLine?:number;endLine?:number}>;
};

/** Resolve model-selected addresses into exact host-owned source excerpts. */
export function resolveObservationSources<T extends ReviewSourceSubmission>(observations: ReadonlyArray<T>, sources: ReadonlyMap<string,string>): Array<Omit<T,"sourceRefs"> & {sourceRefs:Array<{sourceId:string;quote:string}>}> {
  const resolved = observations.map((observation,index) => ({...observation,sourceRefs:(observation.sourceRefs ?? []).map((reference,referenceIndex)=>{
    if (reference.quote !== undefined) return {sourceId:reference.sourceId,quote:reference.quote};
    const source = sources.get(reference.sourceId);
    const lines = source === undefined ? undefined : sourceLineBodies(source);
    const start=reference.startLine, end=reference.endLine;
    if (!lines || !Number.isInteger(start) || !Number.isInteger(end) || start! < 1 || end! < start! || end! > lines.length) {
      const details={code:"REVIEW_SOURCE_RANGE_INVALID",path:`/observations/${index}/sourceRefs/${referenceIndex}`,sourceId:reference.sourceId,startLine:start,endLine:end,lineCount:lines?.length??0};
      throw Object.assign(new Error(JSON.stringify(details)),details);
    }
    const quote=lines.slice(start!-1,end).join("\n");
    if (!quote.trim()) {
      const nearbyLines=[...new Set([start!-2,start!-1,end!,end!+1])].filter(index=>index>=0&&index<lines!.length&&lines![index]!.trim()).map(index=>({line:index+1,text:lines![index]!.slice(0,400)}));
      const details={code:"REVIEW_SOURCE_REQUIRED",path:`/observations/${index}/sourceRefs/${referenceIndex}`,sourceId:reference.sourceId,startLine:start,endLine:end,lineCount:lines!.length,nearbyLines,instruction:"This selection contains only blank lines. Select the numbered source lines that actually support this finding, or withdraw it. Preserve other valid references."};
      throw Object.assign(new Error(JSON.stringify(details)),details);
    }
    return {sourceId:reference.sourceId,quote};
  })}));
  validateObservationSources(resolved,sources);
  return resolved;
}

export function validateObservationSources(observations: ReadonlyArray<Observation>, sources: ReadonlyMap<string, string>): void {
  const issues: Array<{code: string; path: string; observationCode: string; sourceId?: string; quote?: string}> = [];
  for (const [index, observation] of observations.entries()) {
    if (!observation.sourceRefs?.length && observation.assessment !== "unavailable") issues.push({code:"REVIEW_SOURCE_REQUIRED",path:`/observations/${index}/sourceRefs`,observationCode:observation.code});
    for (const [referenceIndex, reference] of (observation.sourceRefs ?? []).entries()) {
      if (!sources.get(reference.sourceId)?.includes(reference.quote)) issues.push({
        code:"REVIEW_SOURCE_MISMATCH",path:`/observations/${index}/sourceRefs/${referenceIndex}`,observationCode:observation.code,
        sourceId:reference.sourceId,quote:reference.quote.slice(0,1000),
      });
    }
  }
  if (issues.length > 0) {
    const code = issues[0]!.code;
    const details = {code,issues:issues.slice(0,16),issueCount:issues.length,sourceIds:[...sources.keys()],
      instruction:"Use exact excerpts from the named source for these references, or withdraw unsupported findings. Keep valid references unchanged."};
    throw Object.assign(new Error(JSON.stringify(details)),details);
  }
}
