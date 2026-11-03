import path from "node:path";

/** A compiled trial identity cannot inherit a daily data-dir environment override. */
export function resolveTrialProfile(
  buildProfile: unknown,
  home: string,
  appData: string,
  instance?: string,
): { dataDir: string; userDataDir: string } | null {
  if (buildProfile === null) return null;
  if (
    typeof buildProfile !== "string" ||
    !/^[a-z0-9][a-z0-9-]{0,47}$/.test(buildProfile)
  )
    throw new Error("invalid_trial_profile");
  if (instance !== undefined && !/^[a-z0-9][a-z0-9-]{0,31}$/.test(instance))
    throw new Error("invalid_trial_instance");
  const identity =
    instance === undefined ? buildProfile : `${buildProfile}-${instance}`;
  return {
    dataDir: path.join(home, `.one-memory-trial-${identity}`),
    userDataDir: path.join(appData, `One Memory Trial ${identity}`),
  };
}
