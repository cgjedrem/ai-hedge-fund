import type { ReactNode } from "react";

import { EmptyState } from "@/components/page";

export interface TableColumn<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyTitle = "No records yet",
  emptyDescription = "Saved records will appear here.",
}: {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border/80">
      <table className="w-full min-w-[560px] border-collapse text-left text-xs">
        <thead className="bg-white/[0.025]">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`mono whitespace-nowrap px-4 py-3 text-[9px] font-medium uppercase tracking-[0.15em] text-muted-foreground ${
                  column.align === "right" ? "text-right" : ""
                }`}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)} className="transition-colors hover:bg-white/[0.025]">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`px-4 py-3.5 align-middle text-muted-foreground ${
                    column.align === "right" ? "text-right" : ""
                  }`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
