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
    runners: { available: true, count: 0, stale_count: 0, stale_unverified_count: 0, ownership_unknown_count: 0 },
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
    expect(screen.getByText("Restart required")).toBeVisible();
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
          restart_reasons: ["stored-version-changed", "active-capture-stale"],
          active: { available: true, count: 2, stale_count: 1 },
        })}
      />,
    );
    expect(screen.getByText("v4", { selector: "p" })).toBeVisible();
    expect(screen.getByText("v3 · started at v2")).toBeVisible();
    expect(screen.getByText("2 active · 1 on an older version")).toBeVisible();
    expect(screen.getByText(/saves from this page are rejected as stale/)).toBeVisible();
    expect(screen.getByText(/never hot-swapped and a server restart would not change it/)).toBeVisible();
  });

  it("requires restart of active work captured before a settings update without implying hot-swap", () => {
    render(
      <ConfigurationProvenancePanel
        configuration={provenance({
          restart_required: true,
          restart_reasons: ["active-capture-stale"],
          active: { available: true, count: 1, stale_count: 1 },
        })}
      />,
    );
    expect(screen.getByText("Restart required")).toBeVisible();
    expect(screen.getByText(/never switched to the new settings/)).toBeVisible();
    expect(screen.getByText(/next provider call or start is denied \(fail-closed\)/)).toBeVisible();
    expect(screen.getByText(/A server restart does not change captured work/)).toBeVisible();
    expect(screen.getByText(/never restarts the server or running work/)).toBeVisible();
    expect(screen.queryByText(/No restart is needed/)).toBeNull();
    expect(screen.queryByText(/older version stays in force/)).toBeNull();
  });

  it("requires a stop and start of a paper runner launched on an older settings version", () => {
    render(
      <ConfigurationProvenancePanel
        configuration={provenance({
          restart_required: true,
          restart_reasons: ["owned-runner-stale"],
          runners: { available: true, count: 1, stale_count: 1, stale_unverified_count: 1, ownership_unknown_count: 0 },
        })}
      />,
    );
    expect(screen.getByText("Restart required")).toBeVisible();
    expect(screen.getByText(/1 paper runner live · 1 on an\s+older version · 1 version unknown/)).toBeVisible();
    expect(screen.getByText(/Runners do not re-check settings after launch: it keeps its captured version until it stops or expires/)).toBeVisible();
    expect(screen.getByText(/This page does not stop it, and a server restart does not change it/)).toBeVisible();
    expect(screen.queryByText(/offline recovery is required/)).toBeNull();
  });

  it("routes runners whose owner is unverified to offline recovery instead of stop and start", () => {
    render(
      <ConfigurationProvenancePanel
        configuration={provenance({
          restart_required: true,
          restart_reasons: ["owned-runner-unverified"],
          runners: { available: true, count: 0, stale_count: 0, stale_unverified_count: 0, ownership_unknown_count: 2 },
        })}
      />,
    );
    expect(screen.getByText(/0 paper runners live · 0 on an\s+older version · 2 owner unverified/)).toBeVisible();
    expect(screen.getByText(/cannot be stopped or restarted from the paper page; offline recovery is required/)).toBeVisible();
    expect(screen.queryByText(/Stop it from its paper fund page/)).toBeNull();
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
    expect(screen.getByText(/does not erase the captured version or switch the work to another key/)).toBeVisible();
    expect(screen.getByText(/captured version remains in private storage/)).toBeVisible();
  });

  it("does not infer stored values when the stored record is unavailable", () => {
    render(<ConfigurationProvenancePanel configuration={provenance({ stored: { available: false, version: null, present: false } })} />);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(1);
  });
});
