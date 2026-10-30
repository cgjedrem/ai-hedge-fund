import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CurvePoint } from "@/lib/types";
import { money } from "@/lib/utils";

export function EquityChart({
  data,
  title = "Recorded equity",
  description = "Close-to-close · recorded ledger values only",
}: {
  data: CurvePoint[];
  title?: string;
  description?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        </div>
        <span className="mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">USD</span>
      </CardHeader>
      <CardContent>
        {data.length < 2 ? (
          <div className="flex h-[220px] items-center justify-center text-xs text-muted-foreground">
            Two recorded sessions are required to draw a curve.
          </div>
        ) : (
          <div className="h-[220px] w-full" data-testid="equity-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148, 163, 184, 0.12)" vertical={false} />
                <XAxis
                  dataKey="session"
                  tickFormatter={(value: string) => value.slice(5)}
                  stroke="#53616d"
                  tick={{ fill: "#82909b", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  width={72}
                  tickFormatter={(value: number) => money(value, 0)}
                  stroke="#53616d"
                  tick={{ fill: "#82909b", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  domain={["dataMin - 1000", "dataMax + 1000"]}
                />
                <ChartTooltip
                  contentStyle={{
                    background: "#10161d",
                    border: "1px solid rgba(148, 163, 184, 0.22)",
                    borderRadius: 10,
                    color: "#e5edf2",
                    fontSize: 12,
                  }}
                  formatter={(value: number, name: string) => [money(value, 2), name]}
                  labelFormatter={(value: string) => value}
                />
                <Legend
                  wrapperStyle={{ color: "#9aa7b1", fontSize: 11, paddingTop: 8 }}
                  iconType="circle"
                  iconSize={7}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark_nav"
                  name="Benchmark"
                  stroke="#758696"
                  strokeDasharray="4 5"
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 3 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="nav"
                  name="Fund NAV"
                  stroke="#28d5bd"
                  strokeWidth={2.2}
                  dot={false}
                  activeDot={{ r: 4, fill: "#28d5bd", stroke: "#071412", strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
