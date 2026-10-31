import "@testing-library/jest-dom/vitest";

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
