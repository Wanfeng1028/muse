/** Which project the caller is in, as far as the host will say.
 *
 * Needed because memories recorded in a project carry that project's scope,
 * and a scope cannot be constructed outside Core. Naming the directory is
 * the only way in.
 *
 * The server's own working directory is not the answer. Some hosts spawn an
 * MCP server with the user's home as cwd (for example `/Users/example`) while
 * the workspace is handed
 * over in the environment as `WORKSPACE_FOLDER_PATHS`. Trusting `cwd` there
 * would name the home directory as the project — and on this machine home is
 * itself a recorded workspace, so a project's recall would quietly include
 * memories from unrelated home-rooted sessions.
 *
 * So: take what the host declares; otherwise take `cwd`, which is right for
 * a command run in a project and for hosts that spawn their server there;
 * and never accept the home directory as a project, because that is what a
 * host which told us nothing looks like.
 */

export interface WorkspaceSources {
  env: NodeJS.ProcessEnv;
  cwd: string;
  home: string;
}

export function resolveHostWorkspacePath(
  sources: WorkspaceSources,
): string | undefined {
  const declared = firstPath(sources.env.WORKSPACE_FOLDER_PATHS);
  if (declared !== undefined) return declared;
  const cwd = normalize(sources.cwd);
  if (cwd === undefined) return undefined;
  return cwd === normalize(sources.home) ? undefined : cwd;
}

/** Multi-root windows list every folder; the first is the one we can name.
 *
 * Recall takes a single directory, so a window with several roots reaches
 * only the first of them. Left as-is deliberately: no multi-root sample has
 * been seen, so the delimiter is a guess beyond the comma, and inventing
 * more here would be an unverified mechanism.
 */
function firstPath(value: string | undefined): string | undefined {
  if (!value) return undefined;
  for (const candidate of value.split(",")) {
    const normalized = normalize(candidate);
    if (normalized !== undefined) return normalized;
  }
  return undefined;
}

function normalize(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed?.startsWith("/")) return undefined;
  // A trailing separator would make the same directory hash differently than
  // the identity an import recorded for it.
  const withoutTrailing =
    trimmed.length > 1 ? trimmed.replace(/\/+$/, "") : trimmed;
  return withoutTrailing === "" ? "/" : withoutTrailing;
}
