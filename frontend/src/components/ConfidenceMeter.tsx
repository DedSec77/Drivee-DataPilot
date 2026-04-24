import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Gauge, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const COMPONENT_LABELS: Record<string, string> = {
  self_consistency: "согласованность",
  schema_relevance: "релевантность схемы",
  explain_passed: "прошёл EXPLAIN",
  simplicity: "простота",
  time_filter_ok: "фильтр по времени",
  llm_self_conf: "уверенность модели",
  critic_fixed: "исправлен критиком",
};

type Props = {
  value: number;
  components?: Record<string, number>;

  bare?: boolean;
};

export function ConfidenceMeter({ value, components, bare = false }: Props) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone =
    pct >= 75
      ? { label: "высокая", bar: "bg-foreground", text: "text-foreground" }
      : pct >= 60
        ? {
            label: "средняя",
            bar: "bg-muted-foreground",
            text: "text-muted-foreground",
          }
        : {
            label: "низкая",
            bar: "bg-destructive",
            text: "text-destructive-foreground",
          };

  const infoPopover = components && (
    <HoverCard openDelay={100}>
      <HoverCardTrigger asChild>
        <button className="text-muted-foreground hover:text-foreground transition-colors">
          <Info size={12} />
        </button>
      </HoverCardTrigger>
      <HoverCardContent align="end" className="w-72">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Из чего складывается
        </div>
        <ul className="space-y-1 text-xs">
          {Object.entries(components).map(([k, v]) => {
            const num = typeof v === "number" && Number.isFinite(v) ? v : 0;
            return (
              <li key={k} className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">
                  {COMPONENT_LABELS[k] ?? k}
                </span>
                <span className="font-mono tabular-nums">{num.toFixed(2)}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-[11px] text-muted-foreground">
          0.35 × согласованность + 0.18 × схема + 0.17 × EXPLAIN +
          0.10 × простота + 0.10 × фильтр по времени + 0.10 × уверенность модели
        </p>
      </HoverCardContent>
    </HoverCard>
  );

  if (bare) {
    return (
      <div className="flex items-center gap-2">
        <Gauge size={11} className="shrink-0 text-muted-foreground" />
        <span className="font-mono text-xs tabular-nums">{pct}%</span>
        <span className={cn("text-[10px] font-medium uppercase tracking-wider", tone.text)}>
          {tone.label}
        </span>
        <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className={cn("absolute inset-y-0 left-0", tone.bar)}
            style={{ width: `${pct}%` }}
          />
        </div>
        {infoPopover}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Gauge size={14} className="text-muted-foreground" />
          Уверенность
        </CardTitle>
        {infoPopover}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-bold tabular-nums">{pct}%</span>
          <span className={cn("text-xs font-medium", tone.text)}>
            {tone.label}
          </span>
        </div>
        <Progress value={pct} indicatorClassName={tone.bar} className="mt-2" />
      </CardContent>
    </Card>
  );
}
