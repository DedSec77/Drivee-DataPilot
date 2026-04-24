import { useEffect, useState } from "react";
import { RefreshCw, ScrollText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getQueryLog } from "@/api";
import type { QueryLogItem } from "@/types";

const BLOCK_CODES = new Set([
  "NON_SELECT",
  "DENY_TABLE",
  "UNKNOWN_TABLE",
  "PII_COLUMN",
  "NO_TIME_FILTER",
  "TOO_EXPENSIVE",
  "TOO_MANY_JOINS",
  "FORBIDDEN_STMT",
]);

function VerdictBadge({ verdict }: { verdict: string | null }) {
  if (!verdict) return <Badge variant="secondary">—</Badge>;
  const v = verdict.toUpperCase();
  if (v === "OK") return <Badge variant="success">ok</Badge>;
  if (v === "CLARIFY") return <Badge variant="warning">уточнение</Badge>;
  if (BLOCK_CODES.has(v)) {
    return <Badge variant="destructive">{v}</Badge>;
  }
  return <Badge variant="outline">{v}</Badge>;
}

export function QueryLogPage() {
  const [items, setItems] = useState<QueryLogItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await getQueryLog(200));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ScrollText size={16} className="text-muted-foreground" />
            Журнал запросов
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            История всех запросов. Последние {items.length}, включая
            блокировки защитой и диалоги уточнения.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw size={12} /> Обновить
        </Button>
      </div>

      {loading ? (
        <Skeleton className="h-96" />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="max-h-[640px] overflow-auto scrollbar-thin">
              <Table className="table-fixed">
                <TableHeader className="sticky top-0 bg-card">
                  <TableRow>
                    <TableHead className="w-14 whitespace-nowrap">№</TableHead>
                    <TableHead className="w-40 whitespace-nowrap">время</TableHead>
                    <TableHead className="w-32 whitespace-nowrap">вердикт</TableHead>
                    <TableHead className="w-24 whitespace-nowrap text-right">уверенность</TableHead>
                    <TableHead className="w-14 whitespace-nowrap text-right">строк</TableHead>
                    <TableHead className="w-14 whitespace-nowrap text-right">мс</TableHead>
                    <TableHead className="w-auto whitespace-nowrap">вопрос</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">
                        Пока нет запросов. Задайте вопрос на странице Чат.
                      </TableCell>
                    </TableRow>
                  )}
                  {items.map((it) => (
                    <TableRow key={it.log_id} className="align-middle">
                      <TableCell className="py-2 font-mono text-xs">
                        {it.log_id}
                      </TableCell>
                      <TableCell className="py-2 text-xs text-muted-foreground whitespace-nowrap">
                        {it.ts
                          ? new Date(it.ts).toLocaleString("ru-RU", {
                              hour12: false,
                            })
                          : "—"}
                      </TableCell>
                      <TableCell className="py-2">
                        <VerdictBadge verdict={it.guard_verdict} />
                      </TableCell>
                      <TableCell className="py-2 text-right font-mono tabular-nums text-xs">
                        {it.confidence != null ? it.confidence.toFixed(2) : "—"}
                      </TableCell>
                      <TableCell className="py-2 text-right font-mono tabular-nums text-xs">
                        {it.result_rows ?? "—"}
                      </TableCell>
                      <TableCell className="py-2 text-right font-mono tabular-nums text-xs text-muted-foreground">
                        {it.exec_ms ?? "—"}
                      </TableCell>
                      <TableCell className="py-2">
                        <div
                          className="truncate text-sm"
                          title={it.nl_question ?? ""}
                        >
                          {it.nl_question ?? "—"}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
