export interface DisplayPreferenceSnapshot {
  reduceMotion: boolean;
  reduceTransparency: boolean;
  revision: number;
}

export class DisplayPreferences {
  private motion: boolean | undefined;
  private transparency: boolean | undefined;
  private snapshot: DisplayPreferenceSnapshot | null = null;

  constructor(
    private readonly readMotion: () => unknown,
    private readonly readTransparency: () => unknown,
  ) {}

  read(): DisplayPreferenceSnapshot | null {
    this.motion = readBoolean(this.readMotion) ?? this.motion;
    this.transparency = readBoolean(this.readTransparency) ?? this.transparency;
    if (this.motion === undefined || this.transparency === undefined)
      return null;
    if (
      !this.snapshot ||
      this.snapshot.reduceMotion !== this.motion ||
      this.snapshot.reduceTransparency !== this.transparency
    ) {
      this.snapshot = {
        reduceMotion: this.motion,
        reduceTransparency: this.transparency,
        revision: this.snapshot ? this.snapshot.revision + 1 : 0,
      };
    }
    return { ...this.snapshot };
  }
}

function readBoolean(read: () => unknown): boolean | undefined {
  try {
    const value = read();
    return typeof value === "boolean" ? value : undefined;
  } catch {
    // A failed read must not turn an already known accessibility choice off.
    return undefined;
  }
}

export function displayPreferencePayload(
  value: unknown,
): DisplayPreferenceSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Partial<DisplayPreferenceSnapshot>;
  if (
    typeof data.reduceMotion !== "boolean" ||
    typeof data.reduceTransparency !== "boolean" ||
    typeof data.revision !== "number" ||
    !Number.isSafeInteger(data.revision) ||
    data.revision < 0
  )
    return null;
  return {
    reduceMotion: data.reduceMotion,
    reduceTransparency: data.reduceTransparency,
    revision: data.revision,
  };
}
