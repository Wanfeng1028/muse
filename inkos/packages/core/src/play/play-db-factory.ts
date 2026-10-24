import { PlayDB } from "./play-db.js";
import type { PlayGraphSnapshot } from "./play-db.js";
import type { PlayReducerDB } from "./play-reducer.js";

export interface PlayGraphDB extends PlayReducerDB {
  readonly snapshot: () => PlayGraphSnapshot;
  readonly replaceWithSnapshot: (snapshot: PlayGraphSnapshot) => void;
  readonly close?: () => void;
}

export function createPlayDB(runDir: string): PlayGraphDB {
  return new PlayDB(runDir);
}
