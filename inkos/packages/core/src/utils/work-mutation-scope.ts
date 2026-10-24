import { AsyncLocalStorage } from "node:async_hooks";
import { resolve } from "node:path";
const owners = new AsyncLocalStorage<ReadonlySet<string>>();
const queues = new Map<string, Promise<void>>();
const key = (root: string, workId: string) => `${resolve(root)}\0${workId}`;
export function ownsWorkMutation(root: string, workId: string): boolean { return owners.getStore()?.has(key(root, workId)) ?? false; }
export async function withWorkMutationScope<T>(root: string, workId: string, acquire: () => Promise<() => Promise<void>>, task: () => Promise<T>): Promise<T> {
  if (ownsWorkMutation(root, workId)) return task();
  const release = await acquire();
  try { return await owners.run(new Set([...(owners.getStore() ?? []), key(root, workId)]), task); }
  finally { await release(); }
}

/** Share the same queue for whole actions and short snapshot/commit phases. */
export async function runInWorkMutationQueue<T>(key: string, task: () => Promise<T>): Promise<T> {
  const previous = queues.get(key) ?? Promise.resolve();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const queued = previous.catch(() => undefined).then(() => gate);
  queues.set(key, queued);
  await previous.catch(() => undefined);
  try { return await task(); }
  finally { release(); if (queues.get(key) === queued) queues.delete(key); }
}
