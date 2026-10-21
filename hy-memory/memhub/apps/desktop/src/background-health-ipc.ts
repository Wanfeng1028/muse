import {
  type BackgroundHealth,
  inspectBackgroundHealth,
} from "@one-memory/runtime-control";

const CHANNEL = "one-memory:get-background-health";

export function installBackgroundHealthIpc<Event>(options: {
  ipc: {
    handle(
      name: string,
      handler: (event: Event, ...args: unknown[]) => Promise<unknown>,
    ): unknown;
    removeHandler(name: string): void;
  };
  dataDir: string;
  requireTrustedWindow(event: Event): unknown;
  inspect?: (options: { dataDir: string }) => Promise<BackgroundHealth>;
}): () => void {
  let closed = false;
  let flight: Promise<BackgroundHealth> | null = null;
  options.ipc.handle(CHANNEL, async (event, ...args) => {
    if (closed) throw Error("background_health_closed");
    options.requireTrustedWindow(event);
    if (args.length) throw Error("background_health_arguments_rejected");
    const current =
      flight ??
      (options.inspect ?? inspectBackgroundHealth)({
        dataDir: options.dataDir,
      });
    flight = current;
    try {
      const result = await current;
      if (closed) throw Error("background_health_closed");
      options.requireTrustedWindow(event);
      return { ...result };
    } finally {
      if (flight === current) flight = null;
    }
  });
  return () => {
    if (closed) return;
    closed = true;
    options.ipc.removeHandler(CHANNEL);
  };
}
