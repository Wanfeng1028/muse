/** Minimal TOML editing for hosts that keep MCP servers in `config.toml`.
 *
 * The file is edited as text rather than parsed and re-emitted: a real user's
 * `config.toml` carries comments and ordering that a naive round-trip would
 * silently discard. Only the `mcp_servers.<name>` tables this installer owns
 * are ever rewritten; every other byte is preserved exactly.
 */

/** One TOML table, including the comment lines attached above its header. */
export interface TomlBlock {
  /** Dotted table name, e.g. `mcp_servers.one-memory`. */
  header: string;
  /** Verbatim text, comments included, ending with a newline. */
  text: string;
}

export interface TomlDocument {
  /** Key/value lines before the first table header. */
  preamble: string;
  blocks: TomlBlock[];
}

const HEADER = /^\s*\[\[?([^\]]+)\]\]?\s*$/;
const COMMENT = /^\s*#/;

export function parseTomlDocument(raw: string): TomlDocument {
  const lines = raw.split("\n");
  const starts: Array<{ start: number; header: string }> = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = HEADER.exec(lines[index]);
    if (!match) continue;
    // Comments sitting directly above a header describe that table, so they
    // travel with it; a blank line means they belong to what came before.
    let start = index;
    while (start > 0 && COMMENT.test(lines[start - 1])) start -= 1;
    starts.push({ start, header: match[1].trim() });
  }
  if (starts.length === 0) {
    return { preamble: raw, blocks: [] };
  }
  const blocks = starts.map(({ start, header }, position) => {
    const end = starts[position + 1]?.start ?? lines.length;
    return { header, text: `${lines.slice(start, end).join("\n")}` };
  });
  return { preamble: lines.slice(0, starts[0].start).join("\n"), blocks };
}

export function serializeTomlDocument(document: TomlDocument): string {
  const parts = [document.preamble, ...document.blocks.map((b) => b.text)];
  const text = parts.filter((part) => part !== "").join("\n");
  return text.endsWith("\n") ? text : `${text}\n`;
}

/** Indices of the tables making up one MCP server, sub-tables included. */
export function serverBlockIndices(
  document: TomlDocument,
  serverName: string,
): number[] {
  const root = `mcp_servers.${serverName}`;
  return document.blocks.flatMap((block, index) =>
    block.header === root || block.header.startsWith(`${root}.`) ? [index] : [],
  );
}

export interface TomlServer {
  command: string;
  args: string[];
  env: Record<string, string>;
}

/** Read one MCP server back, or null when the tables are not the shape we write. */
export function readTomlServer(
  document: TomlDocument,
  serverName: string,
): TomlServer | null {
  const indices = serverBlockIndices(document, serverName);
  if (indices.length === 0) return null;
  const root = `mcp_servers.${serverName}`;
  let command: string | null = null;
  let args: string[] | null = null;
  const env: Record<string, string> = {};
  for (const index of indices) {
    const block = document.blocks[index];
    const entries = readEntries(block.text);
    if (block.header === root) {
      const rawCommand = entries.get("command");
      const rawArgs = entries.get("args");
      command = rawCommand === undefined ? null : readString(rawCommand);
      args = rawArgs === undefined ? null : readStringArray(rawArgs);
    } else if (block.header === `${root}.env`) {
      for (const [key, value] of entries) {
        const parsed = readString(value);
        if (parsed !== null) env[key] = parsed;
      }
    }
  }
  if (command === null || args === null) return null;
  return { command, args, env };
}

export function renderTomlServer(
  serverName: string,
  server: TomlServer,
): TomlBlock[] {
  const root = `mcp_servers.${quoteHeaderSegment(serverName)}`;
  const blocks: TomlBlock[] = [
    {
      header: `mcp_servers.${serverName}`,
      text: [
        `[${root}]`,
        `command = ${quote(server.command)}`,
        `args = [${server.args.map(quote).join(", ")}]`,
        "",
      ].join("\n"),
    },
  ];
  const env = Object.entries(server.env);
  if (env.length > 0) {
    blocks.push({
      header: `mcp_servers.${serverName}.env`,
      text: [
        `[${root}.env]`,
        ...env.map(([key, value]) => `${quoteKey(key)} = ${quote(value)}`),
        "",
      ].join("\n"),
    });
  }
  return blocks;
}

function readEntries(text: string): Map<string, string> {
  const entries = new Map<string, string>();
  for (const line of text.split("\n")) {
    if (COMMENT.test(line) || HEADER.test(line)) continue;
    const separator = line.indexOf("=");
    if (separator === -1) continue;
    const key = line.slice(0, separator).trim().replace(/^"|"$/g, "");
    if (key) entries.set(key, line.slice(separator + 1).trim());
  }
  return entries;
}

function readString(raw: string): string | null {
  if (raw.length < 2 || !raw.startsWith('"') || !raw.endsWith('"')) return null;
  return unescapeBasic(raw.slice(1, -1));
}

function readStringArray(raw: string): string[] | null {
  if (!raw.startsWith("[") || !raw.endsWith("]")) return null;
  const body = raw.slice(1, -1).trim();
  if (body === "") return [];
  const values: string[] = [];
  // Split on commas that sit outside a quoted string.
  let current = "";
  let quoted = false;
  let escaped = false;
  for (const character of body) {
    if (escaped) {
      current += character;
      escaped = false;
      continue;
    }
    if (character === "\\") {
      current += character;
      escaped = true;
      continue;
    }
    if (character === '"') {
      quoted = !quoted;
      current += character;
      continue;
    }
    if (character === "," && !quoted) {
      values.push(current);
      current = "";
      continue;
    }
    current += character;
  }
  values.push(current);
  const parsed = values.map((value) => readString(value.trim()));
  return parsed.every((value): value is string => value !== null)
    ? parsed
    : null;
}

function unescapeBasic(value: string): string {
  return value.replace(/\\(["\\nrt])/g, (_match, character: string) => {
    if (character === "n") return "\n";
    if (character === "r") return "\r";
    if (character === "t") return "\t";
    return character;
  });
}

function quote(value: string): string {
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
  return `"${escaped}"`;
}

/** Bare keys allow only these characters; anything else must be quoted. */
function quoteKey(key: string): string {
  return /^[A-Za-z0-9_-]+$/.test(key) ? key : quote(key);
}

function quoteHeaderSegment(segment: string): string {
  return /^[A-Za-z0-9_-]+$/.test(segment) ? segment : quote(segment);
}
