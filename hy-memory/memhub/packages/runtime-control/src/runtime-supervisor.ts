import type { HealthResponse } from "@one-memory/contracts";
import { type DiagnosticSink, diagnosticError } from "./diagnostic-log.js";

export interface RuntimeCore {
  readonly instanceId: string;
  readonly apiToken: string;
  readonly port: number;
  start(): Promise<HealthResponse>;
  stop(): Promise<void>;
}

export interface RuntimeSidecar {
  start(): Promise<unknown>;
  stop(): Promise<void>;
}

/** A sidecar fault observed AFTER a successful start.
 *
 * The Broker runs inside the Runtime process, so a JS-level fault there
 * (an unhandled rejection from a request handler, an `error` event on the
 * server) would otherwise take the whole daemon down. The documented contract
 * is the opposite: the outer Runtime stays alive and the state degrades. This
 * record is what the supervisor exposes so `background-health` can report
 * `broker=unhealthy` + overall `degraded` instead of `stopped`. */
export interface RuntimeSidecarFault {
  code: string;
  at: number;
}

export interface RuntimeConnection {
  coreBaseUrl: string;
  coreApiToken: string;
  instanceId: string;
}

export interface RuntimeSupervisorOptions {
  core: RuntimeCore;
  createSidecar(
    connection: RuntimeConnection,
    reportFault: (code: string) => void,
  ): RuntimeSidecar;
  diagnostics?: DiagnosticSink;
  /** Notified exactly once, on the first post-start sidecar fault. Used by the
   * outer service to publish a durable `degraded` status without polling. */
  onSidecarFault?: (fault: RuntimeSidecarFault) => void;
}

/** Owns one complete local Runtime lifecycle without depending on Electron. */
export class RuntimeSupervisor {
  private readonly core: RuntimeCore;
  private readonly createSidecar: RuntimeSupervisorOptions["createSidecar"];
  private readonly diagnostics?: DiagnosticSink;
  private readonly onSidecarFault?: RuntimeSupervisorOptions["onSidecarFault"];
  private sidecar: RuntimeSidecar | null = null;
  private sidecarFault: RuntimeSidecarFault | null = null;
  private started = false;
  private stopping: Promise<void> | null = null;

  constructor(options: RuntimeSupervisorOptions) {
    this.core = options.core;
    this.createSidecar = options.createSidecar;
    this.diagnostics = options.diagnostics;
    this.onSidecarFault = options.onSidecarFault;
  }

  get connection(): RuntimeConnection {
    if (!this.started) throw new Error("MemHub Runtime is not running");
    return this.currentConnection();
  }

  /** The first post-start sidecar fault, if any. Never clears on its own: a
   * fault must not be masked by a later healthy read. A successful restart of
   * the sidecar (elsewhere) is the only thing that would clear it, and this
   * build deliberately does not restart a failed sidecar. */
  get sidecarFaultState(): RuntimeSidecarFault | null {
    return this.sidecarFault;
  }

  /** Sidecar health as the supervisor last observed it. `failed` is a captured
   * post-start fault; `stopped` is a clean drain; `running` is the normal case.
   * Read by the outer Runtime when publishing its own status receipt. */
  get sidecarState(): "running" | "failed" | "stopped" {
    if (this.sidecarFault !== null) return "failed";
    if (this.sidecar !== null) return "running";
    return "stopped";
  }

  async start(): Promise<HealthResponse> {
    if (this.started || this.sidecar || this.stopping) {
      throw new Error("MemHub Runtime supervisor already started");
    }
    const started = Date.now();
    await this.diagnostics?.log({
      level: "info",
      component: "runtime.supervisor",
      event: "runtime.starting",
      outcome: "started",
    });
    let coreStarted = false;
    let phase: "core" | "sidecar" = "core";
    try {
      const health = await this.core.start();
      coreStarted = true;
      phase = "sidecar";
      const sidecar = this.createSidecar(this.currentConnection(), (code) =>
        this.recordSidecarFault(code),
      );
      this.sidecar = sidecar;
      await sidecar.start();
      this.started = true;
      await this.diagnostics?.log({
        level: "info",
        component: "runtime.supervisor",
        event: "runtime.ready",
        outcome: "succeeded",
        instance_id: this.core.instanceId,
        duration_ms: Date.now() - started,
      });
      return health;
    } catch (error) {
      await this.diagnostics?.log({
        level: "error",
        component: "runtime.supervisor",
        event: "runtime.start_failed",
        outcome: "failed",
        instance_id: this.core.instanceId,
        duration_ms: Date.now() - started,
        error_code: "runtime_start_failed",
        details: { phase },
        ...diagnosticError(error),
      });
      await this.sidecar?.stop();
      if (coreStarted) await this.core.stop();
      this.sidecar = null;
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    const sidecar = this.sidecar;
    this.started = false;
    this.stopping = (async () => {
      const started = Date.now();
      await this.diagnostics?.log({
        level: "info",
        component: "runtime.supervisor",
        event: "runtime.stopping",
        outcome: "started",
        instance_id: this.core.instanceId,
      });
      await sidecar?.stop();
      await this.core.stop();
      this.sidecar = null;
      await this.diagnostics?.log({
        level: "info",
        component: "runtime.supervisor",
        event: "runtime.stopped",
        outcome: "succeeded",
        duration_ms: Date.now() - started,
      });
    })();
    try {
      await this.stopping;
    } finally {
      this.stopping = null;
    }
  }

  async restart(): Promise<HealthResponse> {
    await this.stop();
    return this.start();
  }

  private currentConnection(): RuntimeConnection {
    return Object.freeze({
      coreBaseUrl: `http://127.0.0.1:${this.core.port}`,
      coreApiToken: this.core.apiToken,
      instanceId: this.core.instanceId,
    });
  }

  /** Capture a sidecar fault without letting it escape.
   *
   * This is the fault-isolation boundary: a Broker fault must degrade the
   * Runtime, never terminate it. The first fault is retained, later ones are
   * ignored so a fault loop cannot grow unbounded state, and nothing here
   * throws into the caller (which is often an event handler). */
  private recordSidecarFault(code: string): void {
    if (this.sidecarFault !== null) return;
    this.sidecarFault = Object.freeze({
      code: code || "runtime_sidecar_failed",
      at: Date.now(),
    });
    void this.diagnostics?.log({
      level: "error",
      component: "runtime.supervisor",
      event: "runtime.sidecar_failed",
      outcome: "failed",
      instance_id: this.core.instanceId,
      error_code: this.sidecarFault.code,
    });
    try {
      this.onSidecarFault?.(this.sidecarFault);
    } catch {
      // A fault observer must never turn one failure into a fatal one.
    }
  }
}
