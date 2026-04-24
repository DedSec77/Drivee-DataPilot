import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BarChart3,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  Rows3,
  ShieldAlert,
  Table2,
} from "lucide-react";
import * as XLSX from "xlsx";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "@/components/ui/sonner";

type DataCell = string | number | null;

type Props = {
  columns: string[];
  rows: DataCell[][];
  hint: "bar" | "line" | "pie" | "table" | "empty" | null;

  bare?: boolean;
};

const PIE_PALETTE = [
  "hsl(263 65% 60%)",
  "hsl(180 65% 55%)",
  "hsl(40 90% 60%)",
  "hsl(340 70% 55%)",
  "hsl(140 55% 50%)",
  "hsl(220 60% 60%)",
  "hsl(20 80% 60%)",
];

const PII_PATTERNS: { test: RegExp; mask: (v: string) => string }[] = [
  { test: /(^|_)phone(_|$|number)/i, mask: () => "+7***" },
  { test: /(^|_)email(_|$|hash)/i, mask: () => "***@***.***" },
  { test: /(^|_)full_?name|first_?name|last_?name(_|$)/i, mask: () => "***" },
  { test: /(^|_)passport(_|$)/i, mask: () => "****-******" },
  { test: /(^|_)pan(_|$)/i, mask: (v) => maskCardLike(v) },
  { test: /(^|_)cvv(_|$)/i, mask: () => "***" },
];

function maskCardLike(v: string): string {
  const digits = v.replace(/\D/g, "");
  if (digits.length < 4) return "****";
  return `**** **** **** ${digits.slice(-4)}`;
}

function isPiiColumn(col: string): boolean {
  return PII_PATTERNS.some((p) => p.test.test(col));
}

function maskValue(col: string, v: DataCell): DataCell {
  if (v == null) return v;
  for (const p of PII_PATTERNS) {
    if (p.test.test(col)) return p.mask(String(v));
  }
  return v;
}

function maskRow(columns: string[], row: DataCell[]): DataCell[] {
  return row.map((v, i) => maskValue(columns[i] ?? "", v));
}

function downloadBlob(name: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function csvOf(columns: string[], rows: DataCell[][]): string {
  const esc = (v: DataCell) => {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = columns.join(",");
  const body = rows.map((r) => r.map(esc).join(",")).join("\n");
  return head + "\n" + body;
}

export function ResultChart({ columns, rows, hint, bare = false }: Props) {
  const empty = !rows?.length || !columns?.length;

  const piiCols = useMemo(
    () => (empty ? [] : columns.filter(isPiiColumn)),
    [columns, empty]
  );
  const hasPii = piiCols.length > 0;

  const safeRows = useMemo(
    () => (hasPii ? rows.map((r) => maskRow(columns, r)) : rows),
    [rows, columns, hasPii]
  );

  const data = !empty
    ? safeRows.map((r) => {
        const obj: Record<string, DataCell> = {};
        columns.forEach((c, i) => (obj[c] = r[i]));
        return obj;
      })
    : [];

  const numericCols = !empty
    ? columns.filter((c) =>
        data.every((d) => d[c] == null || typeof d[c] === "number")
      )
    : [];
  const xCol = !empty
    ? columns.find((c) => !numericCols.includes(c)) ?? columns[0]
    : "";
  const yCol = !empty ? (numericCols[0] ?? columns[1] ?? "") : "";

  const defaultTab = empty ? "table" : hint === "table" ? "table" : "chart";
  const isLine = hint === "line";
  const isPie = hint === "pie";

  const xTickInterval =
    data.length > 24 ? Math.max(1, Math.ceil(data.length / 12) - 1) : 0;
  const xTickAngle = data.length > 12 ? -30 : 0;
  const xTickHeight = data.length > 12 ? 60 : 36;

  const onCSV = () => {
    downloadBlob("drivee-result.csv", csvOf(columns, safeRows), "text/csv");
    toast.success("CSV скачан", {
      description: hasPii ? "PII-колонки замаскированы" : undefined,
    });
  };
  const onJSON = () => {
    const obj = safeRows.map((r) =>
      Object.fromEntries(columns.map((c, i) => [c, r[i]]))
    );
    downloadBlob("drivee-result.json", JSON.stringify(obj, null, 2), "application/json");
    toast.success("JSON скачан", {
      description: hasPii ? "PII-колонки замаскированы" : undefined,
    });
  };
  const onXLSX = () => {

    const aoa = [columns, ...safeRows];
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Result");
    XLSX.writeFile(wb, "drivee-result.xlsx");
    toast.success("Excel скачан", {
      description: hasPii ? "PII-колонки замаскированы" : undefined,
    });
  };
  const onPDF = async () => {

    const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
      import("html2canvas"),
      import("jspdf"),
    ]);

    const target =
      (document.querySelector("[data-export-root]") as HTMLElement | null) ??
      document.body;
    const canvas = await html2canvas(target, {
      backgroundColor: "#0a0a0a",
      scale: 2,
      useCORS: true,
    });
    const img = canvas.toDataURL("image/png");

    const pdf = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    const pw = pdf.internal.pageSize.getWidth();
    const ph = pdf.internal.pageSize.getHeight();
    const margin = 8;
    const maxW = pw - margin * 2;
    const maxH = ph - margin * 2;
    const ratio = canvas.width / canvas.height;
    let w = maxW;
    let h = w / ratio;
    if (h > maxH) {
      h = maxH;
      w = h * ratio;
    }
    pdf.addImage(img, "PNG", (pw - w) / 2, (ph - h) / 2, w, h);
    pdf.save("drivee-result.pdf");
    toast.success("PDF скачан", {
      description: hasPii ? "PII-колонки замаскированы" : undefined,
    });
  };

  const inner = (
    <>
      {bare && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="text-[11px] text-muted-foreground">
            {rows.length} строк · {columns.length} колонок
            {hasPii && (
              <Badge variant="destructive" className="ml-2 gap-1">
                <ShieldAlert size={10} /> PII
              </Badge>
            )}
          </div>
          <div className="flex gap-1.5">
            <Button variant="ghost" size="sm" onClick={onCSV} disabled={empty}>
              <Download size={12} /> CSV
            </Button>
            <Button variant="ghost" size="sm" onClick={onXLSX} disabled={empty}>
              <FileSpreadsheet size={12} /> Excel
            </Button>
            <Button variant="ghost" size="sm" onClick={onPDF} disabled={empty}>
              <FileText size={12} /> PDF
            </Button>
            <Button variant="ghost" size="sm" onClick={onJSON} disabled={empty}>
              <FileJson size={12} /> JSON
            </Button>
          </div>
        </div>
      )}
      {empty ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Нет данных для визуализации.
          </div>
        ) : (
          <Tabs defaultValue={defaultTab}>
            <TabsList>
              <TabsTrigger value="chart" className="gap-1">
                <BarChart3 size={12} /> График
              </TabsTrigger>
              <TabsTrigger value="table" className="gap-1">
                <Table2 size={12} /> Таблица
              </TabsTrigger>
              <TabsTrigger value="json" className="gap-1">
                <FileJson size={12} /> JSON
              </TabsTrigger>
            </TabsList>

            <TabsContent value="chart">
              {data.length === 0 || !yCol ? (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  Нет числовой колонки для построения графика.
                </div>
              ) : (
                <div style={{ width: "100%", height: 360, minHeight: 200 }}>
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200}>
                    {isPie ? (
                      <PieChart>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "rgba(10, 10, 10, 0.92)",
                            backdropFilter: "blur(4px)",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: 8,
                            fontSize: 12,
                            color: "hsl(var(--foreground))",
                            boxShadow: "0 10px 30px -10px rgba(0,0,0,0.6)",
                          }}
                          itemStyle={{ color: "hsl(var(--foreground))" }}
                        />
                        <Legend
                          verticalAlign="bottom"
                          wrapperStyle={{
                            fontSize: 11,
                            color: "hsl(var(--muted-foreground))",
                          }}
                        />
                        <Pie
                          data={data}
                          dataKey={yCol}
                          nameKey={xCol}
                          cx="50%"
                          cy="45%"
                          outerRadius={110}
                          innerRadius={45}
                          paddingAngle={2}
                          label={({ name, percent }) => {

                            const pct = Number.isFinite(percent)
                              ? Math.round((percent ?? 0) * 100)
                              : 0;
                            return `${name} · ${pct}%`;
                          }}
                          labelLine={false}
                        >
                          {data.map((_, idx) => (
                            <Cell
                              key={`slice-${idx}`}
                              fill={PIE_PALETTE[idx % PIE_PALETTE.length]}
                            />
                          ))}
                        </Pie>
                      </PieChart>
                    ) : isLine ? (
                      <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                        <XAxis
                          dataKey={xCol}
                          stroke="hsl(var(--muted-foreground))"
                          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                          interval={xTickInterval}
                          minTickGap={16}
                          angle={xTickAngle}
                          textAnchor={xTickAngle === 0 ? "middle" : "end"}
                          height={xTickHeight}
                        />
                        <YAxis
                          stroke="hsl(var(--muted-foreground))"
                          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                          width={56}
                        />
                        <Tooltip
                          cursor={{ stroke: "hsl(var(--border))", strokeDasharray: 3 }}
                          contentStyle={{
                            backgroundColor: "rgba(10, 10, 10, 0.92)",
                            backdropFilter: "blur(4px)",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: 8,
                            fontSize: 12,
                            color: "hsl(var(--foreground))",
                            boxShadow: "0 10px 30px -10px rgba(0,0,0,0.6)",
                          }}
                          labelStyle={{
                            color: "hsl(var(--muted-foreground))",
                            fontSize: 11,
                            marginBottom: 2,
                          }}
                          itemStyle={{ color: "hsl(var(--foreground))" }}
                        />
                        <Line
                          dataKey={yCol}
                          stroke="hsl(var(--foreground))"
                          strokeOpacity={0.9}
                          strokeWidth={2}
                          dot={{ r: 3, fill: "hsl(var(--foreground))" }}
                        />
                      </LineChart>
                    ) : (
                      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                        <XAxis
                          dataKey={xCol}
                          stroke="hsl(var(--muted-foreground))"
                          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                          interval={xTickInterval}
                          minTickGap={16}
                          angle={xTickAngle}
                          textAnchor={xTickAngle === 0 ? "middle" : "end"}
                          height={xTickHeight}
                        />
                        <YAxis
                          stroke="hsl(var(--muted-foreground))"
                          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                          width={56}
                        />
                        <Tooltip
                          cursor={{ fill: "hsl(var(--muted) / 0.3)" }}
                          contentStyle={{
                            backgroundColor: "rgba(10, 10, 10, 0.92)",
                            backdropFilter: "blur(4px)",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: 8,
                            fontSize: 12,
                            color: "hsl(var(--foreground))",
                            boxShadow: "0 10px 30px -10px rgba(0,0,0,0.6)",
                          }}
                          labelStyle={{
                            color: "hsl(var(--muted-foreground))",
                            fontSize: 11,
                            marginBottom: 2,
                          }}
                          itemStyle={{ color: "hsl(var(--foreground))" }}
                        />
                        <Bar
                          dataKey={yCol}
                          fill="hsl(var(--foreground))"
                          fillOpacity={0.85}
                          radius={[4, 4, 0, 0]}
                        />
                      </BarChart>
                    )}
                  </ResponsiveContainer>
                </div>
              )}
            </TabsContent>

            <TabsContent value="table">
              <div className="max-h-96 overflow-auto scrollbar-thin rounded-md border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columns.map((c) => (
                        <TableHead key={c}>
                          <span className="inline-flex items-center gap-1">
                            {c}
                            {isPiiColumn(c) && (
                              <Badge
                                variant="destructive"
                                className="px-1.5 py-0 text-[9px] uppercase"
                              >
                                PII
                              </Badge>
                            )}
                          </span>
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {safeRows.map((r, i) => (
                      <TableRow key={i}>
                        {r.map((v, j) => (
                          <TableCell key={j}>
                            {v == null
                              ? "—"
                              : typeof v === "number"
                                ? Number(v).toLocaleString()
                                : String(v)}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            <TabsContent value="json">
              <pre className="max-h-96 overflow-auto scrollbar-thin rounded-md border border-border bg-background/60 p-3 text-xs">
                <code>
                  {JSON.stringify(
                    safeRows.map((r) =>
                      Object.fromEntries(columns.map((c, i) => [c, r[i]]))
                    ),
                    null,
                    2
                  )}
                </code>
              </pre>
            </TabsContent>
          </Tabs>
        )}
    </>
  );

  if (bare) return <div>{inner}</div>;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Rows3 size={14} className="text-muted-foreground" />
          Результат
          <span className="text-[11px] font-normal text-muted-foreground">
            · {rows.length} строк · {columns.length} колонок
          </span>
          {hasPii && (
            <Badge variant="destructive" className="ml-2 gap-1">
              <ShieldAlert size={11} /> PII замаскирован
            </Badge>
          )}
        </CardTitle>
        <div className="flex gap-1.5">
          <Button variant="outline" size="sm" onClick={onCSV} disabled={empty}>
            <Download size={12} /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={onXLSX} disabled={empty}>
            <FileSpreadsheet size={12} /> Excel
          </Button>
          <Button variant="outline" size="sm" onClick={onPDF} disabled={empty}>
            <FileText size={12} /> PDF
          </Button>
          <Button variant="outline" size="sm" onClick={onJSON} disabled={empty}>
            <FileJson size={12} /> JSON
          </Button>
        </div>
      </CardHeader>
      <CardContent>{inner}</CardContent>
    </Card>
  );
}
