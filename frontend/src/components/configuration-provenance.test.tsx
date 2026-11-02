import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfigurationProvenancePanel } from "@/components/configuration-provenance";
import type { ConfigurationField, ConfigurationProvenance } from "@/lib/types";

function field(name: string, value: unknown, extra: Partial<ConfigurationField> = {}): ConfigurationField {
  return {
    field: name,
    source: "persisted",
    override: null,
    stored_source: "persisted",
    stored: value,
    effective: value,
    redacted: false,
    diverges: false,
    shadowed: false,
    ...extra,
  };
}

function provenance(extra: Partial<ConfigurationProvenance> = {}): ConfigurationProvenance {
  return {
    stored: { available: true, version: 2, present: true },
    effective: { version: 2, startup_version: 2 },
    fields: [
      field("data_provider", "synthetic"),
      field("llm_provider", "Ollama"),
      field("model", "llama3"),
      field("endpoint", null),
      field("timeout_seconds", 60),
      field("parameters", {}),
    ],
    overrides: [],
    restart_required: false,
    restart_reasons: [],
    stored_values: null,
    active: { available: true, count: 0, stale_count: 0 },
    credential_captures: [],
    policy: { hot_reload: false, environment_read_at: "startup", process_environment_credentials_used: false, restart_action: "manual" },
    ...extra,
  };
}

describe("ConfigurationProvenancePanel", () => {
  it("reports agreement when stored, effective and active versions are equal", () => {
    render(<ConfigurationProvenancePanel configuration={provenance()} />);
    expect(screen.getByText("v2", { selector: "p" })).toBeVisible();
    expect(screen.getByText("v2 · started at v2")).toBeVisible();
    expect(screen.getByText(/Stored and effective settings agree\. No restart is needed\./)).toBeVisible();
    expect(screen.queryByText(/Restart required/)).toBeNull();
    expect(within(screen.getByTestId("provenance-model")).getAllByText("llama3")).toHaveLength(2);
  });

  it("names override sources, hides endpoint origins and explains manual restart", () => {
    const configuration = provenance({
      fields: [
        field("model", "llama3", { source: "environment", override: "AIHF_MODEL", effective: "mistral", diverges: true, shadowed: true }),
        field("endpoint", "loopback", { source: "environment", override: "AIHF_ENDPOINT", stored: null, stored_source: "default", effective: "remote", redacted: true, diverges: true }),
      ],
      overrides: [
        { field: "model", source: "environment", variable: "AIHF_MODEL" },
        { field: "endpoint", source: "environment", variable: "AIHF_ENDPOINT" },
      ],
      restart_required: true,
      restart_reasons: ["override-shadows-stored"],
    });
    const { container } = render(<ConfigurationProvenancePanel configuration={configuration} />);
    const model = screen.getByTestId("provenance-model");
    expect(within(model).getByText("Process environment")).toBeVisible();
    expect(within(model).getByText("AIHF_MODEL")).toBeVisible();
    expect(within(model).getByText("Saved value shadowed")).toBeVisible();
    const endpoint = screen.getByTestId("provenance-endpoint");
    expect(within(endpoint).getByText("remote endpoint · origin hidden")).toBeVisible();
    expect(within(endpoint).getByText("Not set")).toBeVisible();
    expect(container.textContent).not.toMatch(/https?:\/\//);
    expect(screen.getByText("Restart required for saved settings to apply everywhere")).toBeVisible();
    expect(screen.getByText(/process environment override shadows a saved value/)).toBeVisible();
    expect(screen.getByText(/never restarts the server.*Restart is a manual operator action/)).toBeVisible();
  });

  it("explains a stored version written after startup and stale active captures", () => {
    render(
      <ConfigurationProvenancePanel
        configuration={provenance({
          stored: { available: true, version: 4, present: true },
          effective: { version: 3, startup_version: 2 },
          restart_required: true,
          restart_reasons: ["stored-version-changed"],
          active: { available: true, count: 2, stale_count: 1 },
        })}
      />,
    );
    expect(screen.getByText("v4", { selector: "p" })).toBeVisible();
    expect(screen.getByText("v3 · started at v2")).toBeVisible();
    expect(screen.getByText("2 active · 1 on an older version")).toBeVisible();
    expect(screen.getByText(/saves from this page are rejected as stale/)).toBeVisible();
    expect(screen.getByText(/never hot-swapped and restarting would not change it/)).toBeVisible();
  });

  it("keeps a captured credential version visible after the saved credential is deleted", () => {
    render(
      <ConfigurationProvenancePanel
        configuration={provenance({
          credential_captures: [
            {
              capture_id: "c".repeat(32),
              subject_id: "fund-alpha",
              status: "running",
              provider: "openai",
              captured_version: 1,
              current_version: 2,
              configured: false,
              captured_version_retained: true,
              state: "deleted-after-capture",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("deleted-after-capture")).toBeVisible();
    expect(screen.getByText(/captured v1 · saved v2/)).toBeVisible();
    expect(screen.getByText(/running work keeps its captured version and is not revoked/)).toBeVisible();
    expect(screen.getByText(/captured version remains in private storage/)).toBeVisible();
  });

  it("does not infer stored values when the stored record is unavailable", () => {
    render(<ConfigurationProvenancePanel configuration={provenance({ stored: { available: false, version: null, present: false } })} />);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
  });
});
