# Acceptance matrix

**Status:** inventory only; no migration acceptance inferred. All 74 discovery rows,
contract obligations, and runtime checks start `PENDING`.
**Authority:** `spec.md`, `discovery.md`, and `docs/governance/web-migration-contract.md`.
**Evidence:** status changes require source-bound evidence in the task-specific evidence
files. A planned test or passing unit test alone does not close native, browser, package,
or runtime obligations.

## Discovery capabilities

| Discovery ID | FR | Acceptance tests | Required disposition | Status |
| --- | --- | --- | --- | --- |
| A01 | FR-001, FR-005 | T077, T080, T086, T091–T093 | Default interactive launch uses desk; no terminal fallback. | PENDING |
| A02 | FR-001, FR-062 | T077, T080, T091–T094 | Retire supported TUI entry only after all retirement gates pass. | PENDING |
| A03 | FR-003, FR-028 | T039, T078, T111, T119 | Recorded/offline/error provenance; malformed mandates remain visible. | PENDING |
| A04 | FR-002 | T079, T083, T087–T089 | Keyboard, focus, command palette, back navigation, narrow-screen and terminal-like presentation. | PENDING |
| A05 | FR-003, FR-009, FR-035, FR-045 | T028, T039, T065, T112, T120 | Explicit refresh updates current operation identity; delayed responses cannot replace newer state. | PENDING |
| A06 | FR-037 | T064–T069, T073–T076 | Corrupt-control Halt is distinct from ledger corruption; Resume needs verified recovery. | PENDING |
| A07 | FR-005, FR-062 | T077, T080, T087, T093 | Clean package serves included assets without Node; missing assets fail actionably. | PENDING |
| B01 | FR-018 | T045, T053, T057, T060 | Supported model catalog and effective-model provenance. | PENDING |
| B02 | FR-018, FR-023 | T045, T053, T057 | Persist next-operation model choice; expose active frozen capture. | PENDING |
| B03 | FR-021, FR-024 | T045, T049, T057, T059 | Key entry is write-only; status/readiness never discloses material. | PENDING |
| B04 | FR-021, FR-022, FR-056 | T008, T013, T045, T050, T059 | Neutral helper provides surgical private credential updates and precedence. | PENDING |
| B05 | FR-024 | T010, T016–T020, T040 | Invalid credentials/configuration/network/owner/halt/replay fail before provider or effects. | PENDING |
| B06 | FR-019 | T045, T052, T053, T060 | Normalized market-data provider is persistent and separately selected. | PENDING |
| B07 | FR-019, FR-024, FR-047 | T010, T052, T110, T117 | Free credential-free data is default; non-point-in-time limitations remain visible. | PENDING |
| B08 | FR-020, FR-024 | T047, T051, T053 | Local endpoint/context/timeout are validated without network; local inference needs no cloud key. | PENDING |
| B09 | FR-020, FR-054 | T047, T051 | Remote endpoint overrides reject secrets, unsupported schemes, redirect and DNS escape. | PENDING |
| B10 | FR-023 | T010, T045, T050, T057, T060 | Active operation keeps frozen settings; runner adoption requires deliberate restart. | PENDING |
| B11 | FR-018, FR-022, FR-023 | T045, T053, T057, T060 | Restart-persistent settings show launch/environment, stored, and safe-default provenance. | PENDING |
| B12 | FR-027 | T045, T058–T062, T096, T099 | G4: retain headless SIM provisioning only; desk shows redacted readiness, not rotating secrets. | PENDING |
| C01 | FR-028 | T046, T055, T060 | Canonical YAML/YML list/detail, collision rules, and malformed-entry errors. | PENDING |
| C02 | FR-028, FR-030 | T046, T048, T054–T056 | Validated create and advanced editor round-trip supported fields without executable input. | PENDING |
| C03 | FR-031 | T046, T054, T056 | Library identity and roster persist unless operator explicitly creates custom composition. | PENDING |
| C04 | FR-029, FR-031 | T046, T048, T056 | Supported analyst subsets, weights, and parameters are editable and validated. | PENDING |
| C05 | FR-029, FR-034, FR-040 | T046, T055, T058, T095–T100 | Universe is separate from template; deployment snapshot is immutable and local-paper-only. | PENDING |
| C06 | FR-032 | T026, T046, T048, T056 | Daily/weekly/monthly/minute cadence round-trips. | PENDING |
| C07 | FR-032 | T026, T046, T048, T056 | One-second floor, time window, timezone, and SIM restrictions remain validated. | PENDING |
| C08 | FR-029, FR-033, FR-035 | T046, T054, T056, T063 | Approval default-off omission and deployed gate state remain canonical. | PENDING |
| C09 | FR-027, FR-029 | T046, T048, T058, T096, T099 | G4: inspect SIM readiness; deny browser SIM deployment and execution. | PENDING |
| C10 | FR-029, FR-030 | T046, T048, T056 | Every supported risk and sleeve-weight field round-trips. | PENDING |
| C11 | FR-029–FR-031 | T046, T054, T056 | Model weights and constructor parameters use authoritative registries; no arbitrary code. | PENDING |
| C12 | FR-029, FR-031 | T046, T054, T056 | Blend, gross target, and dollar-neutrality policy are explicit and validated. | PENDING |
| C13 | FR-029, FR-033 | T046, T054, T056 | Spread, per-share/notional/minimum commissions and default omissions remain canonical. | PENDING |
| C14 | FR-029, FR-030 | T046, T054, T056 | Minimum order threshold and benchmark round-trip with execution validation. | PENDING |
| C15 | FR-028, FR-033 | T046, T054, T055 | Edit is revision-bound and never changes deployed snapshots or pending decisions. | PENDING |
| C16 | FR-028 | T046, T055 | Clone/rename create collision-checked canonical identities under admission. | PENDING |
| C17 | FR-034 | T048, T055–T058 | Builder leads to inspect, deploy, and reviewed run/backtest actions with distinct scopes. | PENDING |
| C18 | FR-041, FR-043 | T095, T101–T104 | Archive is scoped/reversible; G4 denies web lifecycle mutation for SIM deployments. | PENDING |
| D01 | FR-003, FR-050 | T078, T111, T119, T122 | Recorded paper list/detail/history use verified snapshots and independent error states. | PENDING |
| D02 | FR-008, FR-009 | T025, T030, T032, T038, T041, T042 | Runner state binds root, deployment, capture, and process incarnation. | PENDING |
| D03 | FR-006, FR-007, FR-010 | T025, T033, T035, T038, T041, T042 | Explicit reviewed local-paper start shares admission; read/startup/approval never starts work. | PENDING |
| D04 | FR-008, FR-011, FR-062 | T025, T030–T032, T035, T041, T042 | Stop targets only verified owned process and reports safe-boundary quiescence. | PENDING |
| D05 | FR-012 | T025, T037–T042 | Browser/server closure leaves runner unchanged; restart only observes verified owner. | PENDING |
| D06 | FR-009, FR-014 | T026, T033, T034, T041, T042 | Daily backlog is oldest-first, visible, and bounded before admission. | PENDING |
| D07 | FR-014 | T026, T032, T041, T042 | Minute gaps, holidays, lateness, and SIM cutoff preserve canonical behavior. | PENDING |
| D08 | FR-007, FR-014, FR-015, FR-024 | T026, T033–T035, T040, T043 | Manual tick is reviewed, frozen, durable, canonical, and denies runner conflicts. | PENDING |
| D09 | FR-004, FR-014 | T026, T036, T040 | Web review binds explicit dates/backfill; supported headless due/no-work semantics remain. | PENDING |
| D10 | FR-038 | T063, T069–T072, T074 | Latest redo is head-bound, quiescent, local-paper-only; G4 denies SIM redo. | PENDING |
| D11 | FR-015, FR-017, FR-050 | T034, T038, T043, T111, T119, T122 | Stage/progress/report is durable; append failure remains ambiguous and never repeats effects. | PENDING |
| D12 | FR-013, FR-037 | T064, T067, T069, T072–T076 | Emergency Halt blocks new admission through corrupt controls; G4 denies SIM Halt. | PENDING |
| D13 | FR-036 | T063, T068–T072, T074–T076 | Resume requires reconciliation and replay; never starts work; G4 denies SIM Resume. | PENDING |
| D14 | FR-041, FR-042 | T095, T101, T102, T104, T106–T108 | Archive requires verified stopped/quiescent ownership and reversible identity-bound journal. | PENDING |
| D15 | FR-043 | T095, T101, T102, T104–T108 | Replacement creates linked new identity; G4 denies SIM replacement. | PENDING |
| D16 | FR-009, FR-021 | T030, T032, T038, T040 | Diagnostics are bounded, redacted, and owner-bound. | PENDING |
| E01 | FR-025, FR-045 | T017, T109, T114, T115, T120 | Refresh is explicitly authorized; observation and polling never call providers. | PENDING |
| E02 | FR-045, FR-046 | T109, T114, T115, T120 | Estimated values stay separate from recorded NAV and performance. | PENDING |
| E03 | FR-045, FR-046 | T109, T114, T115, T120 | Per-ticker freshness/coverage is explicit; stale or partial values are not complete NAV. | PENDING |
| E04 | FR-035 | T063, T069, T071, T074 | Verdict binds timestamp/source hash; stale state conflicts; G4 denies SIM verdicts. | PENDING |
| E05 | FR-003, FR-035 | T065, T069, T071, T075 | Pending/matching/stale/consumed/expired states refresh without retargeting. | PENDING |
| E06 | FR-036 | T063, T069–T071, T075 | Approval and Run are separate authorizations; G4 denies SIM execution. | PENDING |
| E07 | FR-038 | T063, T068–T072, T074–T076 | Source redo invalidates votes; execution redo preserves matching consumed votes. | PENDING |
| E08 | FR-017, FR-039 | T064, T068, T072–T075 | Post-fill append failure is halted/ambiguous; recovery never retries old effects. | PENDING |
| F01 | FR-047 | T110, T117, T121 | Backtest review binds dates, universe, mandate revision, capture, and data limitation. | PENDING |
| F02 | FR-023, FR-024, FR-047 | T010, T016, T017, T110, T117 | Backtest uses frozen provider/model/mandate capture and preflight denials. | PENDING |
| F03 | FR-048, FR-056 | T008, T110, T116, T117, T121 | Warming/stage/agent progress is available without TUI renderables. | PENDING |
| F04 | FR-050, FR-055 | T008, T111, T119, T122 | Replay, NAV, benchmark, metrics, and scorecards retain precision/provenance. | PENDING |
| F05 | FR-016, FR-017, FR-048 | T011, T018, T110, T117, T121 | Cancellation has safe boundaries; navigation/reload never resubmits. | PENDING |
| F06 | FR-016 | T011, T018, T110, T117, T123 | Restart marks unfinished jobs interrupted; completed results remain discoverable. | PENDING |
| F07 | FR-049 | T111, T118, T121 | Stable bounded pagination/search exceeds 100 rows and exposes malformed records. | PENDING |
| F08 | FR-050 | T111, T119, T122 | Session/day detail preserves proposed versus executed information. | PENDING |
| F09 | FR-050, FR-054 | T111, T119, T122 | Reports retain risk, clamps, orders, fills, weights, tape, theses, costs, and inert text. | PENDING |
| F10 | FR-004, FR-050, FR-056 | T008, T013, T077, T119, T122 | Canonical scorecards render in web and supported headless output; no TUI dependency. | PENDING |
| F11 | FR-041, FR-043 | T095, T101, T103, T118 | Research archive is reversible, scoped, and coordinated with active references. | PENDING |
| F12 | FR-004, FR-051 | T077, T111, T119, T122 | Browser export is canonical; supported headless stdout/output files remain. | PENDING |
| F13 | FR-052 | T110, T116, T121 | Explicit exception: preserve and label daily-grid replay; no intraday parity claim. | PENDING |

## G4 SIM disposition register

These are narrow web-operation exemptions, not broad feature or acceptance passes.
Headless fake-SIM compatibility and exclusive account binding remain required. Every
negative web-operation test remains pending.

| Discovery ID | Web SIM exemption | Required evidence | Status |
| --- | --- | --- | --- |
| B12 | No browser credential/OAuth provisioning or rotating-token storage; redacted readiness only. | T045, T058–T062, T096, T099 | PENDING |
| C05 | No SIM deployment through the desk. | T095–T100, T104 | PENDING |
| C09 | SIM may be selected/readied, but browser deploy/run is denied. | T048, T058, T096, T099, T104 | PENDING |
| C18 | No web archive of a SIM mandate/deployment. | T095, T101, T102, T104 | PENDING |
| D03 | No web SIM start. | T035, T040, T099, T104 | PENDING |
| D04 | No web SIM stop/control. | T035, T040, T099, T104 | PENDING |
| D08 | No web SIM tick/manual execution. | T035, T040, T070, T099 | PENDING |
| D10 | No web SIM redo. | T069, T070, T072 | PENDING |
| D12 | No web SIM Halt mutation. | T067, T069, T072 | PENDING |
| D13 | No web SIM Resume mutation. | T068–T070, T072 | PENDING |
| D14 | No web SIM archive/restore. | T101, T102, T104, T106 | PENDING |
| D15 | No web SIM replacement/redeploy. | T102, T104, T106 | PENDING |
| E04 | No web SIM verdict. | T069, T070, T072 | PENDING |
| E06 | No web SIM Run authorization. | T069, T070, T072 | PENDING |
| E07 | No web SIM redo vote mutation. | T069, T070, T072 | PENDING |

## Explicit non-web exceptions

| Scope | Allowed behavior | Required evidence | Status |
| --- | --- | --- | --- |
| D09, F10, F12 | Retain compatible headless due/no-work/date, scorecard, stdout, and output-file workflows without Textual. | T036, T077, T080, T093 | PENDING |
| F13 | Minute mandates remain labelled daily-grid replay; true historical intraday simulation is out of scope. | T110, T116, T121, T126 | PENDING |
| B12, C09, D03–D15, E04, E06–E07 | G4 web SIM operations are denied; fake headless provisioning/readiness and exclusivity tests remain required. | T058–T062, T070, T096, T099, T104 | PENDING |

## Cross-cutting FR obligations

| FR | Acceptance tests | Required disposition | Status |
| --- | --- | --- | --- |
| FR-053 | T019, T020, T078, T080, T084 | Host/Origin/CSRF, loopback and observer boundaries remain enforced on every route/channel. | PENDING |
| FR-054 | T047, T051, T111, T119 | Untrusted text is inert; redaction and endpoint controls persist across browser, exports, children. | PENDING |
| FR-055 | T008, T013, T063, T068, T119, T130 | Canonical engine, replay, reconciliation, sizing and historical serialization remain authoritative. | PENDING |
| FR-056 | T008, T013, T077 | Neutral helpers and their assertions survive outside TUI imports. | PENDING |
| FR-057 | T004, T127 | Every A01–F13 row links FRs, required tests, or an explicit bounded exception. | PENDING |
| FR-058 | T001, T002, T006, T007, T020, T024 | Every future test uses isolated roots/credentials/dotenv and below-guard fakes. | PENDING |
| FR-059 | T006, T024, T041–T043, T059–T061, T073–T075, T087–T093, T128–T133 | Evidence binds exact source/build/time/environment/fixtures and reopens after fixes. | PENDING |
| FR-060 | T127–T136 | Test-first convergence, three independent QA passes, final review, and open human-review PR. | PENDING |
| FR-061 | T127, T134 | User-authorized governance amendment and paid/free/scheduled policy are explicit; no suite pass inferred. | PENDING |
| FR-062 | T080, T087–T094, T127–T136 | No TUI retirement before fresh package, Windows/Linux, browser, writer, and parity evidence. | PENDING |

## Local-boundary, ledger-money, and human-control findings

| Finding | Required closure | Planned discriminating tests/evidence | Status |
| --- | --- | --- | --- |
| LM1 | All-writer admission, unknown legacy denial, ordered locks, bounded emergency lane. | T009, T014, T015, T021, T027, T073 | PENDING |
| LM2 | Host writer/read-only container observer; no TUI/ttyd services or autorestart. | T078, T080, T084, T087–T093 | PENDING |
| LM3 | Durable reconciliation before Resume after ambiguous fills. | T064, T068, T069, T073, T074 | PENDING |
| LM4 | Exact head/due-set review, bounded backlog, stopped restore. | T026, T033, T036, T095, T101 | PENDING |
| LM5 | Exclusive SIM account binding; web SIM lifecycle exemption. | T096, T099, T104, T106, T108 | PENDING |
| LB1 | Explicit root, exact dotenv, private captured configuration, safe child environment. | T007, T012, T016, T022 | PENDING |
| LB2 | Read-only container role, loopback publication, host/origin/CSRF guards. | T019, T020, T078, T080, T084 | PENDING |
| LB3 | Credential-bound endpoints, DNS/TLS pinning, redirect/private-address denial. | T047, T051, T017 | PENDING |
| LB4 | Surgical credentials, active capture semantics, Windows ACL/Linux mode proof. | T045, T050, T059 | PENDING |
| LB5 | Tested local NTFS/ext4 identity/lock/replace only; unsupported filesystems deny. | T007, T022 | PENDING |
| HM1 | Authorized amendment without inventing full-suite/baseline success. | T127–T133, T134 | PENDING |
| HM2 | Free default; paid calls require per-operation authorization; all cloud models classified paid. | T010, T017, T052, T109, T117 | PENDING |
| HM3 | Finite scheduled free/local scope and enforced per-call budget; no paid retry. | T010, T017, T109, T117 | PENDING |
| HM4 | Verified detached owner/process incarnation; durable interrupted jobs; no auto-resume. | T025, T030, T031, T037, T041–T043, T123 | PENDING |
| HM5 | Single-use digest confirmation, durable idempotency, approval warning, sidecar provenance. | T011, T018, T023, T063, T069 | PENDING |

## Entry-point, helper, and compose assertions

These checks prevent retirement claims based only on React page coverage. Every row is
pending until its exact supported entrypoint or packaged artifact is exercised.

| Surface | Required assertion | Planned tests/evidence | Status |
| --- | --- | --- | --- |
| No-argument CLI | Opens supported web desk; no TUI fallback/import. | T077, T080, T091–T093 | PENDING |
| Direct TUI entry | No supported Textual launcher remains after retirement gate. | T077, T080, T091–T093 | PENDING |
| Headless CLI | Paper/backtest/report/scorecard/control/output commands work without Textual. | T036, T070, T077, T080, T093 | PENDING |
| Helper import closure | `run.py`, `web/services.py`, `check_stock.py`, `llm/test_client.py` use neutral helpers. | T008, T013, T077 | PENDING |
| Helper parity | Cost/report/scorecard/default/schedule/progress semantics retain canonical order and precision. | T008, T013, T077, T111, T119 | PENDING |
| Make/README entrypoints | Documented commands match supported web/headless flags and safety defaults. | T086, T134 | PENDING |
| Dockerfile | Supported image has assets but no Textual, Node runtime, ttyd, or automatic runner. | T080, T084, T087–T093 | PENDING |
| `docker-compose.yml` | Observer is read-only, credential/provider-free, host-loopback published, no writer proxy/autostart. | T078, T080, T084, T087–T093 | PENDING |
| `docker-compose.linux.yml` | Same observer rules; no claim without actual Linux evidence. | T078, T080, T084, T042, T087–T093 | PENDING |
| Wheel/sdist | Desk assets included; runtime starts without Node; missing assets fail actionably. | T080, T087, T093 | PENDING |
| Browser fixture | Explicit test root/8876, no unrelated server reuse, external requests denied, owned outputs. | T003, T128 | PENDING |
| Preview-port isolation | No acceptance or launch path uses creator port 8765. | T003, T006, T128 | PENDING |
