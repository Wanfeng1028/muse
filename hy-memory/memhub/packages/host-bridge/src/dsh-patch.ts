/** Editing for DeepSeek Harness, whose profile config is a patch list.
 *
 * Every other host keeps a map of servers keyed by name. Harness instead keeps
 * an ordered list of loader patch entries, and an external MCP server is one
 * plugin row inside an `insert` list — the grammar was read off the installed
 * `@deepseek-ai/dsh-base` bundle patch, and `dsh --dump-config` on this machine
 * accepted the row this module writes:
 *
 *     - insert:
 *         - id: one-memory-recall
 *           name: '@deepseek-ai/dsh-mcp-client'
 *           config:
 *             serverName: onememory
 *             transport: stdio
 *             command: ...
 *
 * Parsing this file and writing it back is not an option, and not merely for
 * formatting's sake. The document is allowed to carry `!!js` expressions — the
 * user layer's own header says so, and the composed tree on this machine holds
 * rows like `disabled: !!js process.platform === 'win32'`. A YAML library
 * without those tags registered refuses the file outright; one that loads them
 * loosely would evaluate or discard them. Either way the user's config is
 * damaged by a tool that was only asked to add a server.
 *
 * So the managed row is written as a text block between sentinels and removed
 * by the same sentinels. Every byte outside them is never read as YAML at all.
 */

export interface DshServer {
  command: string;
  args: string[];
  env: Record<string, string>;
}

const BEGIN = "# >>> one-memory recall — managed block, do not edit >>>";
const END = "# <<< one-memory recall — managed block <<<";

/** The row id and tool namespace this module owns.
 *
 * `serverName` becomes the prefix of every bridged tool name
 * (`mcp__onememory__om_recall`), and Harness constrains it to
 * `[A-Za-z0-9_-]{1,32}` — which is why it is not spelled `one-memory`.
 */
export const DSH_ROW_ID = "one-memory-recall";
export const DSH_SERVER_NAME = "onememory";

interface Block {
  /** Line index of the begin sentinel. */
  start: number;
  /** Line index of the end sentinel. */
  end: number;
}

function findBlock(lines: string[]): Block | null {
  const start = lines.indexOf(BEGIN);
  if (start === -1) return null;
  const end = lines.indexOf(END, start + 1);
  if (end === -1) return null;
  return { start, end };
}

/** True when the document carries a row of ours that is not inside our block.
 *
 * A row left behind by an older install, or written by hand, cannot be removed
 * by sentinel and must not be silently duplicated: two rows with one id is a
 * load error in Harness, so installing over it would break the host.
 */
export function hasUnmanagedRow(raw: string): boolean {
  const lines = raw.split("\n");
  const block = findBlock(lines);
  return lines.some((line, index) => {
    if (block !== null && index > block.start && index < block.end)
      return false;
    return new RegExp(`^\\s*-?\\s*id:\\s*['"]?${DSH_ROW_ID}['"]?\\s*$`).test(
      line,
    );
  });
}

export function readDshServer(raw: string): DshServer | null {
  const lines = raw.split("\n");
  const block = findBlock(lines);
  if (block === null) return null;
  const body = lines.slice(block.start + 1, block.end);
  const command = scalarAfter(body, "command");
  if (command === null) return null;
  return {
    command,
    args: flowSequence(body, "args"),
    env: mapping(body, "env"),
  };
}

export function putDshServer(raw: string, server: DshServer): string {
  const rendered = render(server);
  const lines = raw.split("\n");
  const block = findBlock(lines);
  if (block !== null) {
    return [
      ...lines.slice(0, block.start),
      ...rendered,
      ...lines.slice(block.end + 1),
    ].join("\n");
  }
  // A pristine user layer is a comment header over `[]`. That is an empty flow
  // sequence, and a block item cannot simply follow it: the result is two
  // nodes in one document, which the host refuses to load. The `[]` has to go.
  const empty = lines.findIndex((line) => line.trim() === "[]");
  if (empty !== -1) {
    return [
      ...lines.slice(0, empty),
      ...rendered,
      ...lines.slice(empty + 1),
    ].join("\n");
  }
  const prefix = raw === "" || raw.endsWith("\n") ? raw : `${raw}\n`;
  return `${prefix}${rendered.join("\n")}\n`;
}

export function removeDshServer(raw: string): string {
  const lines = raw.split("\n");
  const block = findBlock(lines);
  if (block === null) return raw;
  const remaining = [
    ...lines.slice(0, block.start),
    ...lines.slice(block.end + 1),
  ];
  // Taking the last row out leaves a document with no node, which is null
  // rather than the empty list the host wrote. Put its `[]` back.
  const hasRow = remaining.some((line) => /^\s*-\s/.test(line));
  if (!hasRow) {
    const tail = remaining.findIndex((line) => line.trim() === "");
    const at = tail === -1 ? remaining.length : tail;
    return [...remaining.slice(0, at), "[]", ...remaining.slice(at)].join("\n");
  }
  return remaining.join("\n");
}

function render(server: DshServer): string[] {
  return [
    BEGIN,
    "- insert:",
    `    - id: ${DSH_ROW_ID}`,
    "      name: '@deepseek-ai/dsh-mcp-client'",
    "      config:",
    `        serverName: ${DSH_SERVER_NAME}`,
    "        transport: stdio",
    `        command: ${quote(server.command)}`,
    `        args: [${server.args.map(quote).join(", ")}]`,
    ...(Object.keys(server.env).length > 0
      ? [
          "        env:",
          ...Object.entries(server.env).map(
            ([key, value]) => `          ${key}: ${quote(value)}`,
          ),
        ]
      : []),
    END,
  ];
}

/** Single-quoted always, so a value can never be read as another YAML type.
 *
 * Notably this keeps `'1'` a string. Harness merges `env` into the child
 * process environment, where a number is not a value at all.
 */
function quote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

function unquote(raw: string): string {
  if (raw.length >= 2 && raw.startsWith("'") && raw.endsWith("'")) {
    return raw.slice(1, -1).replace(/''/g, "'");
  }
  if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
    return raw.slice(1, -1).replace(/\\(.)/g, "$1");
  }
  return raw;
}

function scalarAfter(body: string[], key: string): string | null {
  const pattern = new RegExp(`^\\s*${key}:\\s*(.+)$`);
  for (const line of body) {
    const match = pattern.exec(line);
    if (match) return unquote(match[1].trim());
  }
  return null;
}

function flowSequence(body: string[], key: string): string[] {
  const raw = scalarAfter(body, key);
  if (raw === null || !raw.startsWith("[") || !raw.endsWith("]")) return [];
  const inner = raw.slice(1, -1).trim();
  if (inner === "") return [];
  const values: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < inner.length; index += 1) {
    const character = inner[index];
    if (character === "'") {
      // Doubling is the escape inside a single-quoted scalar, so a pair is a
      // literal quote rather than a close followed by an open.
      if (quoted && inner[index + 1] === "'") {
        current += "''";
        index += 1;
        continue;
      }
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
  return values.map((value) => unquote(value.trim()));
}

function mapping(body: string[], key: string): Record<string, string> {
  const at = body.findIndex((line) =>
    new RegExp(`^\\s*${key}:\\s*$`).test(line),
  );
  if (at === -1) return {};
  const indent = (/^\s*/.exec(body[at])?.[0] ?? "").length;
  const collected: Record<string, string> = {};
  for (const line of body.slice(at + 1)) {
    if (line.trim() === "") continue;
    const own = (/^\s*/.exec(line)?.[0] ?? "").length;
    if (own <= indent) break;
    const match = /^\s*([^\s:]+):\s*(.*)$/.exec(line);
    if (match) collected[match[1]] = unquote(match[2].trim());
  }
  return collected;
}
