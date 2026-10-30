import "@testing-library/jest-dom/vitest";

globalThis.ResizeObserver ??= class ResizeObserver {
  observe(): void {}

  unobserve(): void {}

  disconnect(): void {}
};

Element.prototype.scrollIntoView ??= function scrollIntoView(): void {};
