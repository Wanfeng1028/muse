import { readFile } from "node:fs/promises";
import type { BrokerDiscovery } from "@one-memory/host-bridge";
import axios from "axios";

import { processIsAlive } from "./core-supervisor.js";
import { type DiagnosticSink, diagnosticError } from "./diagnostic-log.js";
import type { RuntimeSidecar } from "./runtime-supervisor.js";

export type RecallBrokerFactory = () => RuntimeSidecar;

export interface RecallBrokerSupervisorOptions {
  discoveryPath: string;
  instanceId: string;
  createBroker: RecallBrokerFactory;
  /** Notified once when a post-start Broker fault is captured. The supervisor
   * itself adds no restart policy; it only makes the fault observable so the
   * outer Runtime can degrade instead of dying. */
  onFault?(code: string): void;
  processIsAlive?: (pid: number) => boolean;
  readBrokerDiscovery?: (path: string) => Promise<BrokerDiscovery>;
  probeBroker?: (discovery: BrokerDiscovery) => Promise<void>;
  diagnostics?: DiagnosticSink;
}

export class RecallBrokerSupervisor implements RuntimeSidecar {
  private readonly options: RecallBrokerSupervisorOptions;
  private owned: RuntimeSidecar | null = null;
  private attached = false;
  private faulted = false;

  constructor(options: RecallBrokerSupervisorOptions) {
    this.options = options;
  }

  async start(): Promise<void> {
    if (this.owned || this.attached) {
      throw new Error("MemHub Recall Broker supervisor already started");
    }
    if (await this.attachExisting()) {
      await this.options.diagnostics?.log({
        level: "info",
        component: "host.broker",
        event: "broker.attached",
        outcome: "succeeded",
        instance_id: this.options.instanceId,
      });
      return;
    }
    const broker = this.options.createBroker();
    this.owned = broker;
    try {
      await broker.start();
      await this.options.diagnostics?.log({
        level: "info",
        component: "host.broker",
        event: "broker.started",
        outcome: "succeeded",
        instance_id: this.options.instanceId,
      });
    } catch (error) {
      await this.options.diagnostics?.log({
        level: "error",
        component: "host.broker",
        event: "broker.start_failed",
        outcome: "failed",
        instance_id: this.options.instanceId,
        error_code: "broker_start_failed",
        ...diagnosticError(error),
      });
      await broker.stop().catch(() => undefined);
      this.owned = null;
      throw error;
    }
  }

  async stop(): Promise<void> {
    const owned = this.owned;
    this.owned = null;
    this.attached = false;
    if (owned) await owned.stop();
    await this.options.diagnostics?.log({
      level: "info",
      component: "host.broker",
      event: "broker.stopped",
      outcome: "succeeded",
      instance_id: this.options.instanceId,
      details: { mode: owned ? "owned" : "attached" },
    });
  }

  /** Idempotently record a post-start Broker fault. Callers are the broker's
   * own failure surfaces (an `error` event, a rejected handler). Must never
   * throw: it runs inside event handlers whose only other option is crashing
   * the Runtime process. */
  reportFault(code: string): void {
    if (this.faulted) return;
    this.faulted = true;
    try {
      this.options.onFault?.(code);
    } catch {
      // Never let the observer become the failure.
    }
  }

  private async attachExisting(): Promise<boolean> {
    const read = this.options.readBrokerDiscovery ?? readBrokerDiscovery;
    let discovery: BrokerDiscovery;
    try {
      discovery = await read(this.options.discoveryPath);
    } catch (error) {
      if (isMissingDiscovery(error)) return false;
      throw new Error("MemHub Recall Broker discovery is invalid", {
        cause: error,
      });
    }
    if (discovery.status !== "running" || discovery.port === null) return false;
    const alive = this.options.processIsAlive ?? processIsAlive;
    if (!alive(discovery.pid)) return false;
    if (discovery.instance_id !== this.options.instanceId) {
      throw new Error("MemHub Recall Broker belongs to another Runtime");
    }
    try {
      const probe = this.options.probeBroker ?? defaultProbeBroker;
      await probe(discovery);
    } catch (error) {
      throw new Error("MemHub Recall Broker identity is unavailable", {
        cause: error,
      });
    }
    this.attached = true;
    return true;
  }
}

async function readBrokerDiscovery(target: string): Promise<BrokerDiscovery> {
  let raw: string;
  try {
    raw = await readFile(target, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      throw new Error("runtime_broker_discovery_missing");
    }
    throw error;
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (error) {
    throw new Error("runtime_broker_discovery_invalid", { cause: error });
  }
  if (!isBrokerDiscovery(value)) {
    throw new Error("runtime_broker_discovery_invalid");
  }
  return value;
}

function isBrokerDiscovery(value: unknown): value is BrokerDiscovery {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<BrokerDiscovery>;
  return (
    item.schema_version === 1 &&
    item.service === "one-memory-recall-broker" &&
    (item.status === "running" || item.status === "stopped") &&
    item.host === "127.0.0.1" &&
    (item.port === null ||
      (Number.isInteger(item.port) &&
        (item.port ?? 0) > 0 &&
        (item.port ?? 0) <= 65_535)) &&
    typeof item.instance_id === "string" &&
    typeof item.pid === "number" &&
    typeof item.updated_at === "string"
  );
}

async function defaultProbeBroker(discovery: BrokerDiscovery): Promise<void> {
  const response = await axios.get<{
    status: string;
    service: string;
    instance_id: string;
  }>(`http://${discovery.host}:${discovery.port}/health`, {
    timeout: 1_000,
    proxy: false,
    maxRedirects: 0,
  });
  if (
    response.data.status !== "ok" ||
    response.data.service !== "one-memory-recall-broker" ||
    response.data.instance_id !== discovery.instance_id
  ) {
    throw new Error("broker identity mismatch");
  }
}

function isMissingDiscovery(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.message === "runtime_broker_discovery_missing" ||
      error.message ===
        "MemHub is not running (broker discovery is unavailable)" ||
      error.message ===
        "One Memory is not running (broker discovery is unavailable)")
  );
}
