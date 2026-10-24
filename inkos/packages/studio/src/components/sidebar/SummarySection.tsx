import { useEffect, useState } from "react";
import { Streamdown } from "streamdown";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import { useChatStore } from "../../store/chat";
import { fetchJson } from "../../hooks/use-api";
import { SidebarCard } from "./SidebarCard";
import { tr } from "../../lib/app-language";
import {
  firstParagraph,
} from "../../lib/truth-display";

const streamdownPlugins = { cjk, code, math, mermaid };

const SIDEBAR_MD_CLASS =
  "text-[15px] text-muted-foreground leading-7 " +
  "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0 " +
  "[&>p+p]:mt-2 [&_strong]:text-foreground [&_strong]:font-medium " +
  "[&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4 [&_li]:my-0.5 " +
  "[&_h1]:hidden [&_h2]:text-[15px] [&_h2]:font-medium [&_h2]:text-foreground [&_h2]:mt-2 [&_h2]:mb-1 " +
  "[&_h3]:text-[15px] [&_h3]:font-medium [&_h3]:text-foreground [&_h3]:mt-2 [&_h3]:mb-1 " +
  "[&_code]:text-[12px] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:bg-secondary/60";

interface SummarySectionProps {
  readonly bookId: string;
}

export function SummarySection({ bookId }: SummarySectionProps) {
  const [worldOverview, setWorldOverview] = useState("");
  const openArtifact = useChatStore((s) => s.openArtifact);
  const bookDataVersion = useChatStore((s) => s.bookDataVersion);

  useEffect(() => {
    let cancelled = false;
    setWorldOverview("");

    fetchJson<{ content: string | null }>(
      `/books/${bookId}/truth/outline/story_frame.md`,
    )
      .then((data) => {
        if (cancelled) return;
        if (data.content) {
          setWorldOverview(firstParagraph(data.content));
        }
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [bookId, bookDataVersion]);

  if (!worldOverview) return null;

  // Worldview etc. is a section inside story_frame.md ("故事基石"); these
  // summary cards are a glance, so offer a button to open the full file.
  const openFull = (
    <button
      onClick={() => openArtifact("outline/story_frame.md")}
      className="mt-2 text-[15px] leading-6 text-primary hover:underline font-['SimSun','Songti_SC','STSong',serif]"
    >
      {tr("查看完整设定 →", "View full foundation →")}
    </button>
  );

  return (
    <>
      {worldOverview && (
        <SidebarCard title={tr("世界观", "World")}>
          <Streamdown className={SIDEBAR_MD_CLASS} plugins={streamdownPlugins}>
            {worldOverview}
          </Streamdown>
          {openFull}
        </SidebarCard>
      )}
    </>
  );
}
