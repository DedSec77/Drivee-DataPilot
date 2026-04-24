import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  BookOpenCheck,
  CheckCircle2,
  ChevronDown,
  Database,
  Link2,
  Loader2,
  PenTool,
  Scale,
  Search,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Vote,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { STREAM_STAGES, type StageEvent, type StreamStage } from "@/types";

type StageMeta = {
  id: StreamStage;
  label: string;
  icon: LucideIcon;

  alwaysVisible?: boolean;
};

const STAGE_META: StageMeta[] = [
  { id: "retrieving", label: "Ищу подходящие сущности и метрики", icon: Search, alwaysVisible: true },

  { id: "linking", label: "Связываю значения из вопроса с данными", icon: Link2 },
  { id: "generating", label: "Генерирую варианты SQL", icon: Wand2, alwaysVisible: true },
  { id: "guarding", label: "Проверяю безопасность кандидатов", icon: ShieldCheck, alwaysVisible: true },
  { id: "scoring", label: "Сравниваю кандидатов и выбираю лучший", icon: Scale, alwaysVisible: true },

  { id: "voting", label: "Голосую по результатам исполнения", icon: Vote },
  { id: "critic", label: "Прошу модель починить SQL", icon: PenTool },
  { id: "executing", label: "Запускаю SQL в Postgres", icon: Database, alwaysVisible: true },
  { id: "verifying", label: "Перепроверяю пустой результат", icon: ScanSearch },
  { id: "interpreting", label: "Собираю объяснение «как я понял»", icon: BookOpenCheck, alwaysVisible: true },
];

const STAGE_INDEX: Record<string, number> = Object.fromEntries(
  STREAM_STAGES.map((s, i) => [s, i])
);

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms} мс`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)} с`;
  return `${Math.round(ms / 1000)} с`;
}

type Props = {
  stages?: StageEvent[];

  pending: boolean;

  fromCache?: boolean;
};

export function ThinkingTrace({ stages, pending, fromCache }: Props) {
  const events = stages ?? [];
  const lastEvent = events[events.length - 1] ?? null;

  const eventCount = events.length;
  const lastReceivedAtRef = useRef<number>(performance.now());
  useEffect(() => {
    lastReceivedAtRef.current = performance.now();
  }, [eventCount]);

  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!pending) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 100);
    return () => window.clearInterval(id);
  }, [pending]);

  const liveMs = useMemo(() => {
    if (!lastEvent) return 0;
    if (!pending) return lastEvent.ms;
    const sinceLast = performance.now() - lastReceivedAtRef.current;
    return Math.max(0, Math.floor(lastEvent.ms + sinceLast));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent, pending, tick]);

  const [open, setOpen] = useState(pending);
  useEffect(() => {

    if (!pending) setOpen(false);
  }, [pending]);

  const firstEventByStage = useMemo(() => {
    const m = new Map<string, StageEvent>();
    for (const e of events) {
      if (!m.has(e.stage)) m.set(e.stage, e);
    }
    return m;
  }, [events]);

  const lastEventByStage = useMemo(() => {
    const m = new Map<string, StageEvent>();
    for (const e of events) m.set(e.stage, e);
    return m;
  }, [events]);

  const stageDuration = (stageId: string): number | undefined => {
    const start = firstEventByStage.get(stageId);
    if (!start) return undefined;
    const startIdx = events.indexOf(start);
    let nextStartMs: number | null = null;
    for (let i = startIdx + 1; i < events.length; i++) {
      if (events[i].stage !== stageId) {
        nextStartMs = events[i].ms;
        break;
      }
    }
    if (nextStartMs !== null) return Math.max(0, nextStartMs - start.ms);

    return Math.max(0, liveMs - start.ms);
  };

  const lastKnownStageEvent = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (STAGE_INDEX[events[i].stage] !== undefined) {
        return events[i];
      }
    }
    return null;
  }, [events]);

  const lastIndex = lastKnownStageEvent
    ? STAGE_INDEX[lastKnownStageEvent.stage]
    : -1;

  const visibleStages = STAGE_META.filter(
    (s) => s.alwaysVisible || lastEventByStage.has(s.id)
  );

  const headerLabel = pending
    ? lastEvent?.label ?? "Готовлю ответ…"
    : `Думал ${formatMs(liveMs)} · ${visibleStages.length} ${pluralizeSteps(visibleStages.length)}`;
  const headerDetail = pending && lastEvent?.detail ? lastEvent.detail : null;

  return (
    <div
      className={cn(
        "rounded-lg border border-border/60 bg-card/30 transition-colors",
        pending && "border-border bg-card/40"
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors",
          "hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
        aria-expanded={open}
      >
        {pending ? (
          <Loader2 size={14} className="shrink-0 animate-spin text-foreground" />
        ) : (
          <Sparkles size={14} className="shrink-0 text-muted-foreground" />
        )}
        <span
          className={cn(
            "min-w-0 flex-1 truncate",
            pending ? "text-foreground" : "text-muted-foreground"
          )}
        >
          <span className="font-medium">{headerLabel}</span>
          {headerDetail && (
            <span className="ml-2 text-xs text-muted-foreground">· {headerDetail}</span>
          )}
        </span>
        {fromCache && (
          <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            из кэша
          </span>
        )}
        {pending && (
          <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
            {formatMs(liveMs)}
          </span>
        )}
        <ChevronDown
          size={14}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <ol className="space-y-0.5 border-t border-border/60 px-2 py-2">
          {visibleStages.map((stage) => {
            const evt = lastEventByStage.get(stage.id);
            const stageIndex = STAGE_META.findIndex((s) => s.id === stage.id);
            const fired = stageIndex !== -1 && stageIndex <= lastIndex;
            const isCurrent = pending && lastEvent?.stage === stage.id;
            const isDone = fired && !isCurrent;
            const status: StageStatus = isCurrent
              ? "current"
              : isDone
                ? "done"
                : "pending";

            const durationMs = fired ? stageDuration(stage.id) : undefined;

            return (
              <StageRow
                key={stage.id}
                meta={stage}
                status={status}
                detail={evt?.detail ?? null}
                ms={durationMs}
              />
            );
          })}
          {events.length === 0 && (
            <li className="px-2 py-1 text-[11px] text-muted-foreground">
              Соединение устанавливается…
            </li>
          )}
        </ol>
      )}
    </div>
  );
}

type StageStatus = "done" | "current" | "pending";

function StageRow({
  meta,
  status,
  detail,
  ms,
}: {
  meta: StageMeta;
  status: StageStatus;
  detail: string | null;
  ms: number | undefined;
}) {
  const Icon = status === "done" ? CheckCircle2 : meta.icon;

  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1 text-xs transition-colors",
        status === "current" && "bg-accent/30",
        status === "pending" && "opacity-50"
      )}
    >
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center",
          status === "pending" ? "text-muted-foreground" : "text-foreground"
        )}
      >
        {status === "current" ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <Icon size={12} />
        )}
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate",
          status === "pending" ? "text-muted-foreground" : "text-foreground"
        )}
      >
        {meta.label}
        {detail && (
          <span className="ml-2 text-[11px] text-muted-foreground">· {detail}</span>
        )}
      </span>
      {typeof ms === "number" && (
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
          {formatMs(ms)}
        </span>
      )}
    </li>
  );
}

function pluralizeSteps(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "шаг";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "шага";
  return "шагов";
}
