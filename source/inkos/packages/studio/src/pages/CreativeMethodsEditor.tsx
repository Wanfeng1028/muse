import { useState } from "react";
import { fetchJson, useApi } from "../hooks/use-api";
import { tr } from "../lib/app-language";

interface Profile { id: string; title: string; requiredSkillIds: string[]; recommendedSkillIds: string[]; [key: string]: unknown; }
interface Document { path: string; content: string; }
export function CreativeMethodsEditor({ profileId }: { profileId: string }) {
  const { data } = useApi<{ profiles: Profile[] }>("/profiles");
  const [profileText, setProfileText] = useState<string | null>(null);
  const [skillId, setSkillId] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [path, setPath] = useState("SKILL.md");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const profile = data?.profiles.find(profile => profile.id === profileId);
  const perform = async (task: () => Promise<void>) => {
    setBusy(true); setMessage("");
    try { await task(); } catch (error) { setMessage(String(error)); } finally { setBusy(false); }
  };
  const openSkill = (id: string) => perform(async () => {
    const result = await fetchJson<{ documents: Document[] }>(`/skills/${encodeURIComponent(id)}/documents`);
    setSkillId(id); setDocuments(result.documents); setPath("SKILL.md");
  });
  return <details className="rounded-xl border border-border bg-card p-5">
    <summary className="cursor-pointer font-semibold">{tr("创作配置与专业方法", "Creative profile and methods")}</summary>
    <p className="my-3 text-sm text-muted-foreground">{tr("项目配置用于后续任务。已有作品版本与执行记录保留其当时的来源。", "Project settings apply to subsequent tasks. Existing revisions and execution records retain their original sources.")}</p>
    {profile && <>
      <button className="rounded border border-border px-3 py-2 text-sm" onClick={() => setProfileText(JSON.stringify(profile, null, 2))}>{tr("编辑作品配置", "Edit profile")}</button>
      {profileText !== null && <div className="mt-3 space-y-2">
        <textarea aria-label={tr("作品配置", "Profile configuration")} className="h-72 w-full rounded border border-border bg-background p-3 font-mono text-sm" value={profileText} onChange={event => setProfileText(event.target.value)} />
        <button disabled={busy} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground" onClick={() => void perform(async () => {
          await fetchJson(`/profiles/${encodeURIComponent(profileId)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: profileText });
          setMessage(tr("作品配置已保存。", "Profile saved."));
        })}>{tr("保存作品配置", "Save profile")}</button>
        <button disabled={busy} className="ml-3 rounded border border-border px-3 py-2 text-sm" onClick={() => void perform(async () => {
          await fetchJson("/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: profileText });
          setMessage(tr("新类型已保存，可在创作对话中使用其 ID 创建作品。", "New profile saved. Use its ID in the creation chat."));
        })}>{tr("保存为新类型（请先更改 ID）", "Save as new profile (change ID first)")}</button>
      </div>}
      <div className="my-4 flex flex-wrap gap-2">{[...new Set([...profile.requiredSkillIds, ...profile.recommendedSkillIds])].map(id => <button key={id} className="rounded border border-border px-3 py-2 text-sm" onClick={() => void openSkill(id)}>{id}</button>)}</div>
    </>}
    {skillId && <div className="space-y-3">
      <label className="text-sm font-medium">{skillId}</label>
      <select aria-label={tr("方法文档", "Method document")} className="ml-3 rounded border border-border bg-background p-2" value={path} onChange={event => setPath(event.target.value)}>{documents.map(document => <option key={document.path}>{document.path}</option>)}</select>
      <textarea aria-label={tr("方法正文", "Method text")} className="h-80 w-full rounded border border-border bg-background p-3 font-mono text-sm" value={documents.find(document => document.path === path)?.content ?? ""} onChange={event => setDocuments(documents.map(document => document.path === path ? { ...document, content: event.target.value } : document))} />
      <button disabled={busy} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground" onClick={() => void perform(async () => {
        await fetchJson(`/skills/${encodeURIComponent(skillId)}/documents`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ documents }) });
        setMessage(tr("项目方法与参考文档已保存。", "Project method and references saved."));
      })}>{tr("保存项目方法", "Save project method")}</button>
    </div>}
    {message && <p role="status" className="mt-3 whitespace-pre-wrap text-sm">{message}</p>}
  </details>;
}
