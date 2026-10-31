import { Activity, ArrowUpRight, Command, Search, Settings2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { CommandPalette } from "@/components/command-palette";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useDesk, DeskProvider } from "@/lib/hooks";
import { BacktestsPage } from "@/pages/backtests";
import { BuilderPage } from "@/pages/builder";
import { HomePage } from "@/pages/home";
import { MandateDetailPage, MandatesPage } from "@/pages/mandates";
import { PaperDetailPage, PaperPage, PaperScorecardPage, SessionReportPage } from "@/pages/paper";
import { ResearchPage, ResearchReportPage } from "@/pages/research";
import { SettingsPage } from "@/pages/settings";

const navigation = [
  { label: "Overview", path: "/", icon: Activity },
  { label: "Mandates", path: "/mandates", icon: ShieldCheck },
  { label: "Builder", path: "/builder", icon: ArrowUpRight },
  { label: "Paper funds", path: "/paper", icon: Activity },
  { label: "Research", path: "/research", icon: Search },
  { label: "Backtests", path: "/backtests", icon: Command },
  { label: "Settings", path: "/settings", icon: Settings2 },
];

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function DeskFrame() {
  const { capabilities, capabilityError } = useDesk();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        if (isEditable(event.target)) return;
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => setPaletteOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only z-[200] focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-black"
      >
        Skip to content
      </a>
      <div className="mx-auto flex min-h-screen max-w-[1680px]">
        <aside className="hidden w-[242px] shrink-0 border-r border-border/80 bg-black/10 px-4 py-5 lg:flex lg:flex-col">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <p className="mono text-[11px] font-semibold tracking-[0.18em] text-foreground">AIHF</p>
              <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Trading desk</p>
            </div>
          </div>
          <div className="mt-7 flex items-center justify-between rounded-lg border border-border bg-white/[0.025] px-3 py-2.5">
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${capabilities?.mode === "demo" ? "bg-amber-300" : "bg-emerald-300"}`} />
              <span className="text-[11px] text-muted-foreground">
                {capabilities?.mode === "demo" ? "Demo workspace" : "Local workspace"}
              </span>
            </div>
            <span className="mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">offline</span>
          </div>
          <nav className="mt-8 flex-1" aria-label="Primary navigation">
            <p className="mono mb-2 px-3 text-[9px] uppercase tracking-[0.22em] text-muted-foreground/70">
              Workspace
            </p>
            <div className="space-y-1">
              {navigation.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs transition ${
                        isActive
                          ? "bg-accent/10 text-accent"
                          : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
                      }`
                    }
                  >
                    <Icon className="h-4 w-4 opacity-80" />
                    <span>{item.label}</span>
                    {item.path === "/paper" ? (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent/80" />
                    ) : null}
                  </NavLink>
                );
              })}
            </div>
          </nav>
          <Separator className="my-4" />
          <div className="space-y-2 px-2 pb-1">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Mutations</span>
              <Badge variant={capabilities?.writes ? "positive" : "muted"}>
                {capabilities?.writes ? "Enabled" : "Read only"}
              </Badge>
            </div>
            <p className="text-[10px] leading-relaxed text-muted-foreground/80">
              Local process · no remote account · no automatic execution
            </p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border/80 bg-[#090c10]/90 px-4 py-3 backdrop-blur-xl sm:px-7">
            <div className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/25 bg-accent/10 text-accent lg:hidden">
                  <Activity className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="mono truncate text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                    LOCAL / PAPER ENVIRONMENT
                  </p>
                  {capabilityError ? (
                    <p className="mt-0.5 truncate text-xs text-rose-300">{capabilityError}</p>
                  ) : (
                    <p className="mt-0.5 truncate text-xs text-foreground">
                      {capabilities?.mode === "demo" ? "Synthetic demo data" : "Read-only by default"}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={capabilities?.network ? "warning" : "positive"}>
                  {capabilities?.network ? "Network enabled" : "Network off"}
                </Badge>
                <Button
                  variant="secondary"
                  size="sm"
                  className="hidden sm:inline-flex"
                  onClick={() => setPaletteOpen(true)}
                  aria-label="Open command palette"
                >
                  <Search className="h-3.5 w-3.5" />
                  <span>Jump to</span>
                  <kbd className="mono ml-1 rounded border border-border px-1 py-0.5 text-[9px] text-muted-foreground">
                    Ctrl K
                  </kbd>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="sm:hidden"
                  onClick={() => setPaletteOpen(true)}
                  aria-label="Open command palette"
                >
                  <Search className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </header>

          <nav className="flex gap-1 overflow-x-auto border-b border-border/70 px-3 py-2 lg:hidden" aria-label="Mobile navigation">
            {navigation.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  `shrink-0 rounded-md px-3 py-2 text-[11px] ${
                    isActive ? "bg-accent/10 text-accent" : "text-muted-foreground"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <main id="main" className="flex-1 px-4 py-6 sm:px-7 sm:py-8 xl:px-10">
            <div className="mx-auto max-w-[1420px]">
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/mandates" element={<MandatesPage />} />
                <Route path="/mandates/:name" element={<MandateDetailPage />} />
                <Route path="/builder" element={<BuilderPage />} />
                <Route path="/paper" element={<PaperPage />} />
                <Route path="/paper/:name" element={<PaperDetailPage />} />
                <Route path="/paper/:name/scorecard" element={<PaperScorecardPage />} />
                <Route path="/paper/:name/sessions/:session" element={<SessionReportPage />} />
                <Route path="/research" element={<ResearchPage />} />
                <Route path="/research/:reportId" element={<ResearchReportPage />} />
                <Route path="/backtests" element={<BacktestsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </div>
          </main>
          <footer className="border-t border-border/70 px-4 py-3 text-center sm:px-7">
            <p className="mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground/60">
              Educational only · Recorded values are not live quotes · No real orders
            </p>
          </footer>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

export default function App() {
  return (
    <DeskProvider>
      <BrowserRouter>
        <DeskFrame />
      </BrowserRouter>
    </DeskProvider>
  );
}
