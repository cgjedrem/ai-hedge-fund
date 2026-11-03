import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

class TestLockManager implements LockManager {
  private readonly queues = new Map<string, Promise<void>>();

  request<T>(name: string, callback: LockGrantedCallback<T>): Promise<T>;
  request<T>(name: string, options: LockOptions, callback: LockGrantedCallback<T>): Promise<T>;
  async request<T>(name: string, optionsOrCallback: LockOptions | LockGrantedCallback<T>, callback?: LockGrantedCallback<T>): Promise<T> {
    const options = typeof optionsOrCallback === "function" ? {} : optionsOrCallback;
    const granted = typeof optionsOrCallback === "function" ? optionsOrCallback : callback;
    if (!granted) throw new Error("Lock callback is required.");
    const previous = this.queues.get(name) ?? Promise.resolve();
    let release!: () => void;
    const current = new Promise<void>((resolve) => { release = resolve; });
    this.queues.set(name, current);
    try {
      await previous;
      if (options.signal?.aborted) throw options.signal.reason;
      return await granted({ name, mode: options.mode ?? "exclusive" });
    } finally {
      release();
      if (this.queues.get(name) === current) this.queues.delete(name);
    }
  }

  async query(): Promise<LockManagerSnapshot> {
    return { held: [], pending: [] };
  }
}

beforeEach(() => {
  Object.defineProperty(navigator, "locks", { configurable: true, value: new TestLockManager() });
});

globalThis.fetch = async () => {
  throw new Error("Network requests are disabled in Vitest.");
};

if (typeof XMLHttpRequest !== "undefined") {
  Object.defineProperty(XMLHttpRequest.prototype, "open", {
    configurable: true,
    value: () => {
      throw new Error("Network requests are disabled in Vitest.");
    },
  });
}

globalThis.ResizeObserver ??= class ResizeObserver {
  observe(): void {}

  unobserve(): void {}

  disconnect(): void {}
};

Element.prototype.scrollIntoView ??= function scrollIntoView(): void {};
