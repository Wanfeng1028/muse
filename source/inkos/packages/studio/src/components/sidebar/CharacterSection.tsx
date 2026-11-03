import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { useChatStore } from "../../store/chat";
import { fetchJson } from "../../hooks/use-api";
import { SidebarCard } from "./SidebarCard";
import { tr } from "../../lib/app-language";
import { roleFromPath, type RoleRef } from "../../lib/truth-display";

// label 在渲染时经 tr() 取当前语言，不能在模块加载时就固定成一种语言。
const TIER_BADGE: Record<RoleRef["tier"], { zh: string; en: string; color: string }> = {
  major: { zh: "主要", en: "Major", color: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  minor: { zh: "次要", en: "Minor", color: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
};

function RoleEntry({ role }: { readonly role: RoleRef }) {
  const openArtifact = useChatStore((s) => s.openArtifact);
  const badge = TIER_BADGE[role.tier];
  return (
    <button
      onClick={() => openArtifact(role.path)}
      className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors text-left"
    >
      <Users size={16} className="shrink-0 text-muted-foreground/60" />
      <span className="text-[15px] leading-6 font-medium text-foreground font-['SimSun','Songti_SC','STSong',serif] flex-1 truncate">
        {role.name}
      </span>
      <span className={`text-[12px] px-1.5 py-0.5 rounded-full shrink-0 ${badge.color}`}>
        {tr(badge.zh, badge.en)}
      </span>
    </button>
  );
}

interface CharacterSectionProps {
  readonly bookId: string;
}

export function CharacterSection({ bookId }: CharacterSectionProps) {
  const [roles, setRoles] = useState<ReadonlyArray<RoleRef>>([]);
  const bookDataVersion = useChatStore((s) => s.bookDataVersion);

  useEffect(() => {
    let cancelled = false;
    setRoles([]);

    fetchJson<{ files: ReadonlyArray<{ name: string }> }>(`/books/${bookId}/truth`)
      .then((data) => {
        if (cancelled) return;
        const roleRefs = data.files
          .map((f) => roleFromPath(f.name))
          .filter((r): r is RoleRef => r !== null)
          .sort((a, b) =>
            a.tier === b.tier ? a.name.localeCompare(b.name) : a.tier === "major" ? -1 : 1,
          );

        setRoles(roleRefs);
      })
      .catch(() => {
        if (!cancelled) {
          setRoles([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [bookId, bookDataVersion]);

  if (roles.length === 0) return null;

  return (
    <SidebarCard title={tr("角色", "Characters")}>
      <div className="space-y-1.5">
        {roles.map((role) => <RoleEntry key={role.path} role={role} />)}
      </div>
    </SidebarCard>
  );
}
