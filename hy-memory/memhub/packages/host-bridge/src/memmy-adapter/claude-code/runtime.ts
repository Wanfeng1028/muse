// MemTensor/MIT-derived Claude integration runtime; see PROVENANCE.md.
import {
  readHostCredentialFile,
  recallThroughBroker,
} from "../../broker-client.js";
import {
  createClaudeEventAdapter,
  type SourceChangeAcceptance,
  type SourceChangeNotification,
} from "./event-adapter.js";
import { readText } from "./private-files.js";
import { type ClaudeRuntimeConfig, runtimeConfig } from "./runtime-config.js";
import { fileSessionStore } from "./session-state.js";

export type NotifySourceChanged = (
  input: SourceChangeNotification,
) => Promise<SourceChangeAcceptance>;
export interface NotificationBinding {
  readonly config: Readonly<ClaudeRuntimeConfig>;
  credentialProvider(): Promise<string>;
}
export type NotificationFactory = (
  binding: NotificationBinding,
) => NotifySourceChanged;
export const CLAUDE_RUNTIME_CAPABILITY = "mh-c01-runtime-v1";

export async function runClaudeHook(
  configFile: string,
  notificationFactory: NotificationFactory,
): Promise<void> {
  if (typeof notificationFactory !== "function")
    throw new Error("notification_transport_required");
  const raw = await readText(configFile, 16_384);
  if (!raw) throw new Error("runtime_config_unavailable");
  const config = runtimeConfig(JSON.parse(raw));
  const credentialProvider = () =>
    readHostCredentialFile(config.credentialFile);
  const notifySourceChanged = notificationFactory({
    config,
    credentialProvider,
  });
  const adapter = createClaudeEventAdapter(
    config,
    {
      recall: (request) =>
        recallThroughBroker(config.discoveryPath, request, {
          credentialProvider,
        }),
      notifySourceChanged,
    },
    fileSessionStore(config.stateDirectory, config.installationId),
    (message) => process.stderr.write(`${message}\n`),
  );
  let bytes = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    const value = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    bytes += value.length;
    if (bytes > 65_536) throw new Error("hook_input_too_large");
    chunks.push(value);
  }
  const result = await adapter.handle(
    JSON.parse(Buffer.concat(chunks).toString("utf8")),
  );
  process.stdout.write(`${JSON.stringify(result.output)}\n`);
}
