import path from "node:path";
import {
  planRecallInstall,
  type RecallHostLayout,
  type RecallInstallPlan,
  type RecallRuntime,
  readInstalledRecallCommand,
} from "./recall-installer.js";

/** A repair worth offering, and what it would change. */
export interface RecallRepoint {
  hostId: string;
  hostLabel: string;
  /** Where the host is pointing now. Null when it names no path at all. */
  from: string | null;
  /** Where the app actually writes. */
  to: string;
  /** The ordinary install plan, so preview and apply are the same ones. */
  plan: RecallInstallPlan;
}

function samePath(left: string, right: string): boolean {
  return path.resolve(left) === path.resolve(right);
}

/** The program the host will launch, apart from where it discovers the app.
 *
 * Discovery lives in the data directory and does not move when the app does.
 * The command and the script beside it were written from inside the app
 * bundle, so an upgrade that only checks discovery leaves the host calling a
 * binary that is no longer there.
 */
function commandDrift(
  installed: Awaited<ReturnType<typeof readInstalledRecallCommand>> & object,
  runtime: RecallRuntime,
): boolean {
  if (!samePath(installed.command, runtime.runtimeCommand)) return true;
  const wanted =
    installed.channel === "cli" ? runtime.recallCliPath : runtime.mcpEntryPath;
  return (
    wanted === undefined ||
    installed.args.length !== 1 ||
    !samePath(installed.args[0], wanted)
  );
}

/** Offer to repoint a host that was installed against the wrong path.
 *
 * The failure this repairs is the one that really happened: three hosts
 * installed against a plausible but wrong discovery file, healthy by every
 * check there was, recalling nothing. A second failure is the command itself:
 * one-click install used to name the binary inside the app bundle, which
 * moves on the next upgrade even when discovery was already right.
 *
 * Deliberately not keyed off the verdict. `unreachable` also covers the app
 * simply not running yet, where the entry is already correct and repointing
 * would change nothing: offering it there would send someone to edit a config
 * that is right while the actual fix is to open the app. So the question asked
 * here is the narrow one — does the host point somewhere other than where the
 * app writes, either the discovery file or the program — and the answer is
 * null whenever it does not.
 *
 * Returns a plan rather than performing the repair, so the repair goes through
 * the same plan / preview / apply the user already sees for an install,
 * including its fingerprint against a file that moved in between.
 */
export async function planRecallRepoint(
  layout: RecallHostLayout,
  runtime: RecallRuntime,
): Promise<RecallRepoint | null> {
  const installed = await readInstalledRecallCommand(layout);
  // Nothing installed is not a repair; it is an install, and offering one as
  // the other would put a "fix this" in front of a host the user never asked
  // to have anything in.
  if (installed === null) return null;
  const wanted = runtime.discoveryPath;
  if (wanted === undefined) return null;
  const discoveryDrift =
    installed.discoveryPath === null ||
    !samePath(installed.discoveryPath, wanted);
  if (!discoveryDrift && !commandDrift(installed, runtime)) return null;
  return {
    hostId: layout.hostId,
    hostLabel: layout.hostLabel,
    from: discoveryDrift ? installed.discoveryPath : installed.command,
    to: discoveryDrift ? wanted : runtime.runtimeCommand,
    // Takeover, because the entry being replaced is our own: it is the wrong
    // one we wrote. Without it the plan would treat our own entry as someone
    // else's and refuse to touch it.
    plan: await planRecallInstall(layout, runtime, { takeover: true }),
  };
}
