import { expect, it } from "vitest";

it("blocks direct network requests unless a test installs a fake", async () => {
  await expect(fetch("https://example.invalid")).rejects.toThrow(
    "Network requests are disabled in Vitest.",
  );
});

it("blocks XMLHttpRequest before opening a network connection", () => {
  const request = new XMLHttpRequest();

  expect(() => request.open("GET", "https://example.invalid")).toThrow(
    "Network requests are disabled in Vitest.",
  );
});
