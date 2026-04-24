import { useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  Database,
  Gauge,
  Sparkles,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/sonner";
import { labelGuardRule, tooltipGuardRule } from "@/lib/guardLabels";

type Props = {
  sql: string;
  appliedRules?: string[];
  cost?: number | null;
  rows?: number | null;

  bare?: boolean;
};

type Optimality = {
  level: "lite" | "balanced" | "heavy";
  label: string;
  description: string;
  icon: typeof Zap;
  variant: "success" | "outline" | "destructive";
};

function classifyOptimality(
  sql: string,
  cost: number | null | undefined
): Optimality {
  const joins = (sql.match(/\bjoin\b/gi) ?? []).length;
  const c = cost ?? 0;
  if (joins <= 1 && c < 1_000) {
    return {
      level: "lite",
      label: "Лёгкий запрос",
      description:
        "Минимум JOIN-ов и низкая EXPLAIN-стоимость — задача решена оптимально.",
      icon: Zap,
      variant: "success",
    };
  }
  if (joins <= 3 && c < 100_000) {
    return {
      level: "balanced",
      label: "Сбалансированный",
      description:
        "Запрос использует JOIN-ы по необходимости, оценка стоимости в норме.",
      icon: Sparkles,
      variant: "outline",
    };
  }
  return {
    level: "heavy",
    label: "Тяжёлый запрос",
    description:
      "Много JOIN-ов или высокая EXPLAIN-стоимость. Подумайте о фильтре по периоду или городу.",
    icon: AlertTriangle,
    variant: "destructive",
  };
}

export function SqlPreview({
  sql,
  appliedRules = [],
  cost,
  rows,
  bare = false,
}: Props) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    toast.success("SQL скопирован");
    setTimeout(() => setCopied(false), 1500);
  };

  const body = (
    <div className="space-y-3">
      <div className="flex items-center justify-end">
        <Button variant="outline" size="sm" onClick={onCopy} className="gap-1">
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "OK" : "Копировать"}
        </Button>
      </div>
      <pre className="max-h-72 overflow-auto scrollbar-thin rounded-lg bg-background/60 border border-border p-3 text-xs leading-relaxed">
        <code className="font-mono">{sql}</code>
      </pre>

      {(() => {
        const opt = classifyOptimality(sql, cost);
        const Icon = opt.icon;
        return (
          <div
            className="flex items-start gap-2 rounded-md border border-border bg-card/40 px-3 py-2"
            title={opt.description}
          >
            <Gauge size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Badge variant={opt.variant} className="gap-1">
                  <Icon size={11} /> {opt.label}
                </Badge>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  оптимальность
                </span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                {opt.description}
              </p>
            </div>
          </div>
        );
      })()}

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {cost != null && (
          <Badge variant="success">стоимость: {cost.toFixed(0)}</Badge>
        )}
        {rows != null && (
          <Badge variant="default">~строк: {rows.toLocaleString()}</Badge>
        )}
        {appliedRules.map((r) => (
          <Badge key={r} variant="outline" title={tooltipGuardRule(r)}>
            {labelGuardRule(r)}
          </Badge>
        ))}
      </div>
    </div>
  );

  if (bare) return body;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Database size={14} className="text-muted-foreground" />
          Сгенерированный SQL
        </CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
