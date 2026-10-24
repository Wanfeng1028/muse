import { WorkProfileSchema, type WorkProfile } from "./contracts.js";

export class WorkProfileRegistry {
  private readonly profiles = new Map<string, WorkProfile>();

  register(input: WorkProfile): void {
    const profile = WorkProfileSchema.parse(input);
    if (this.profiles.has(profile.id)) {
      throw new Error(`Work profile already registered: ${profile.id}`);
    }
    this.profiles.set(profile.id, profile);
  }

  replace(input: WorkProfile): void {
    const profile = WorkProfileSchema.parse(input);
    this.profiles.set(profile.id, profile);
  }

  get(id: string): WorkProfile | undefined {
    return this.profiles.get(id);
  }

  require(id: string): WorkProfile {
    const profile = this.profiles.get(id);
    if (!profile) throw new Error(`Unknown work profile: ${id}`);
    return profile;
  }

  list(): ReadonlyArray<WorkProfile> {
    return [...this.profiles.values()].sort((left, right) => left.id.localeCompare(right.id));
  }
}

