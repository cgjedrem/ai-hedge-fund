import { Link } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { EmptyState } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import type { SessionSummary } from "@/lib/types";
import { dateLabel, money, shortHash } from "@/lib/utils";

function sessionDay(value: unknown): { day: string | null; error: string | null } {
  if (value === null || value === undefined || value === "") {
    return { day: null, error: "Missing session timestamp." };
  }
  if (typeof value !== "string") {
    return { day: null, error: "Session timestamp is not a string." };
  }
  const match = /^(\d{4}-\d{2}-\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?$/.exec(value);
  if (!match || match[0] !== value) {
    return { day: null, error: "Unrecognized session timestamp format. Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (New York wall-clock time)." };
  }
  const [year, month, day] = match[1].split("-").map(Number);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year === 0 || month < 1 || month > 12 || day < 1 || day > daysInMonth[month - 1]) {
    return { day: null, error: "Invalid recorded session date." };
  }
  if (match[2] !== undefined && (Number(match[2]) > 23 || Number(match[3]) > 59 || Number(match[4]) > 59)) {
    return { day: null, error: "Invalid recorded session time." };
  }
  return { day: match[1], error: null };
}

export function PaperSessionDays({
  name,
  sessions,
  search,
}: {
  name: string;
  sessions: SessionSummary[];
  search: string;
}) {
  const columns: TableColumn<SessionSummary>[] = [
    {
      key: "session",
      label: "Session",
      render: (item) => {
        const timestamp = typeof item.session === "string" && item.session ? item.session : null;
        const { error } = sessionDay(item.session);
        return (
          <div>
            {timestamp ? (
              <Link
                aria-label={error ? `Recorded session ${JSON.stringify(timestamp)}` : undefined}
                className="mono text-foreground hover:text-accent hover:underline"
                to={`/paper/${encodeURIComponent(name)}/sessions/${encodeURIComponent(timestamp)}`}
              >
                {error ? timestamp : <time dateTime={timestamp}>{dateLabel(timestamp)}</time>}
              </Link>
            ) : <span className="mono">{item.session === undefined ? "No timestamp field recorded" : JSON.stringify(item.session)}</span>}
            {error ? <p className="mt-1 text-xs text-rose-300">{error} This record is not grouped by day.</p> : null}
          </div>
        );
      },
    },
    { key: "nav", label: "NAV", align: "right", render: (item) => <span className="mono text-foreground">{money(item.nav)}</span> },
    { key: "cash", label: "Cash", align: "right", render: (item) => <span className="mono">{money(item.cash)}</span> },
    { key: "orders", label: "Orders / fills", align: "right", render: (item) => <span className="mono">{item.orders} / {item.fills}</span> },
    { key: "hash", label: "Record hash", render: (item) => <span className="mono" title={item.hash}>{shortHash(item.hash)}</span> },
  ];
  if (sessions.length === 0) {
    return (
      <EmptyState
        title={search ? "No matching verified sessions" : "No verified sessions"}
        description={search ? "No session records on this page match the current search." : "This page has no session records to display."}
      />
    );
  }
  const groups: { day: string | null; records: SessionSummary[] }[] = [];
  for (const record of [...sessions].reverse()) {
    const { day } = sessionDay(record.session);
    const previous = groups[groups.length - 1];
    if (day !== null && previous?.day === day) previous.records.push(record);
    else groups.push({ day, records: [record] });
  }
  const timestampErrors = groups
    .filter((group) => group.day === null)
    .flatMap((group) => group.records.map((record) => sessionDay(record.session).error))
    .filter((error): error is string => error !== null);
  return (
    <div className="space-y-5">
      <p className="text-xs leading-relaxed text-muted-foreground">
        Summaries cover only the records loaded on this page{search ? ` matching "${search}"` : ""}.
        {" "}NAV and cash are copied from the first listed record, not a daily close.
        {" "}Summary amounts are shown to cents; table rows retain whole-dollar rounding.
        {" "}Dates and times are shown as recorded; minute sessions use New York wall-clock time without timezone conversion.
      </p>
      {timestampErrors.length > 0 ? (
        <Alert tone="warning" role="alert">
          <p>Some session timestamps could not be verified. All {timestampErrors.length} affected record{timestampErrors.length === 1 ? "" : "s"} remain visible below.</p>
          <ul className="mt-2 space-y-1">
            {[...new Set(timestampErrors)].map((error) => <li key={error}>{error}</li>)}
          </ul>
        </Alert>
      ) : null}
      {groups.map((group, index) => (
        <section
          key={`${group.day ?? "invalid"}-${index}`}
          aria-label={`${group.day ? `${group.day} loaded day summary` : "Ungrouped session records"} (group ${index + 1})`}
          className="space-y-3"
        >
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="mono text-sm font-semibold text-foreground">
                {group.day ? <time dateTime={group.day}>{group.day}</time> : "Unrecognized session date"}
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">{group.records.length} loaded record{group.records.length === 1 ? "" : "s"}</p>
            </div>
            {group.day ? <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
              <div>
                <dt className="text-muted-foreground">NAV (first listed record)</dt>
                <dd className="mono mt-1 text-foreground">{money(group.records[0].nav, 2)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Cash (first listed record)</dt>
                <dd className="mono mt-1 text-foreground">{money(group.records[0].cash, 2)}</dd>
              </div>
            </dl> : null}
          </div>
          <DataTable
            columns={columns}
            rows={group.records}
            rowKey={(item, rowIndex) => `${item.hash}-${rowIndex}`}
            ariaLabel={`${group.day ?? "Unrecognized session date"} session records (group ${index + 1})`}
          />
        </section>
      ))}
    </div>
  );
}
