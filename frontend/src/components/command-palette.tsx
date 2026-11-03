import { Command } from "cmdk";
import { ArrowRight, BarChart3, BriefcaseBusiness, FileText, FlaskConical, Gauge, Home, Settings2, WandSparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

const commands = [
  { label: "Desk overview", path: "/", group: "Navigate", icon: Home },
  { label: "Mandates", path: "/mandates", group: "Navigate", icon: BriefcaseBusiness },
  { label: "Build a mandate", path: "/builder", group: "Navigate", icon: WandSparkles },
  { label: "Paper funds", path: "/paper", group: "Navigate", icon: Gauge },
  { label: "Research reports", path: "/research", group: "Navigate", icon: FileText },
  { label: "Backtest", path: "/backtests", group: "Navigate", icon: FlaskConical },
  { label: "Settings", path: "/settings", group: "Navigate", icon: Settings2 },
  { label: "Scorecards", path: "/paper", group: "Inspect", icon: BarChart3 },
];

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Desk command palette"
      className="fixed left-1/2 top-[18vh] z-[100] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-[#10161d] shadow-[0_24px_80px_rgba(0,0,0,.55)]"
    >
      <div className="flex items-center border-b border-border px-4">
        <Command.Input
          autoFocus
          placeholder="Search pages…"
          className="h-14 w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        <kbd className="mono rounded border border-border px-1.5 py-1 text-[10px] text-muted-foreground">ESC</kbd>
      </div>
      <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-2">
        <Command.Empty className="px-3 py-8 text-center text-xs text-muted-foreground">
          No matching destination.
        </Command.Empty>
        {["Navigate", "Inspect"].map((group) => (
          <Command.Group
            key={group}
            heading={group}
            className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2"
          >
            {commands
              .filter((item) => item.group === group)
              .map((item) => {
                const Icon = item.icon;
                return (
                  <Command.Item
                    key={item.path}
                    value={item.label}
                    onSelect={() => {
                      navigate(item.path);
                      onOpenChange(false);
                    }}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground outline-none aria-selected:bg-white/[0.07] aria-selected:text-foreground"
                  >
                    <Icon className="h-4 w-4 text-accent" />
                    <span>{item.label}</span>
                    <ArrowRight className="ml-auto h-3.5 w-3.5 opacity-40" />
                  </Command.Item>
                );
              })}
          </Command.Group>
        ))}
      </Command.List>
      <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[10px] text-muted-foreground">
        <span>LOCAL DESK · NAVIGATION ONLY</span>
        <span className="mono">↑ ↓ · ENTER</span>
      </div>
    </Command.Dialog>
  );
}
