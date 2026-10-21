import {
  getNativeDisplayPreferences,
  startNativeDisplayPreferences,
  subscribeNativeDisplayPreferences,
} from "./display-preferences";

export function installNativeDisplayStyles(): () => void {
  const root = document.documentElement;
  const keys = ["nativeReduceMotion", "nativeReduceTransparency"] as const;
  const previous = keys.map((key) => root.dataset[key]);
  const update = () => {
    const preferences = getNativeDisplayPreferences();
    root.dataset.nativeReduceMotion = String(
      preferences?.reduceMotion === true,
    );
    root.dataset.nativeReduceTransparency = String(
      preferences?.reduceTransparency === true,
    );
  };
  const unsubscribe = subscribeNativeDisplayPreferences(update);
  const stop = startNativeDisplayPreferences();
  update();
  return () => {
    unsubscribe();
    stop();
    keys.forEach((key, index) => {
      if (previous[index] === undefined) delete root.dataset[key];
      else root.dataset[key] = previous[index];
    });
  };
}
