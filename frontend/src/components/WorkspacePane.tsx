import { useState } from "react";
import {
  BookmarkPlus,
  ChevronDown,
  Clock,
  Database,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { HowIAnswered } from "@/components/HowIAnswered";
import { ResultChart } from "@/components/ResultChart";
import { SqlPreview } from "@/components/SqlPreview";
import { labelGuardRule, tooltipGuardRule } from "@/lib/guardLabels";
import { cn } from "@/lib/utils";
import type { AskResponse } from "@/types";

type Props = {
  resp: AskResponse;
  question: string;
  saving: boolean;
  saveDisabled: boolean;
  onSave: () => void;
  isPinnedArchive?: boolean;
  onUnpin?: () => void;
};

export function WorkspacePane({
  resp,
  question,
  saving,
  saveDisabled,
  onSave,
  isPinnedArchive = false,
  onUnpin,
}: Props) {
  const [sqlOpen, setSqlOpen] = useState(false);
  const [explainerOpen, setExplainerOpen] = useState(false);
  const guardRules = resp.explainer?.guard_rules_applied ?? [];

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" data-export-root>
            <div
        className={cn(
          "flex items-center justify-between gap-3 rounded-lg border px-3 py-1.5 transition-colors",
          isPinnedArchive
            ? "border-amber-500/40 bg-amber-500/5"
            : "border-border bg-card/40"
        )}
      >
        <div className="flex min-w-0 flex-1 items-center gap-2">
          {isPinnedArchive && (
            <Clock
              size={12}
              className="shrink-0 text-amber-400"
              aria-label="Просмотр прошлого ответа"
            />
          )}
          <div
            className="min-w-0 flex-1 truncate text-sm text-foreground/90"
            title={question}
          >
            {question}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {isPinnedArchive && onUnpin && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs text-amber-300 hover:text-amber-200"
              onClick={onUnpin}
              title="Вернуться к последнему ответу"
            >
              <X size={11} /> к последнему
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={onSave}
            disabled={saveDisabled}
            title={
              saveDisabled && isPinnedArchive
                ? "Сохранить можно только последний ответ"
                : undefined
            }
          >
            <BookmarkPlus size={11} />
            {saving ? "..." : "Сохранить"}
          </Button>
        </div>
      </div>

            <section
        className={cn(
          "flex flex-col overflow-hidden rounded-lg border border-border bg-card/40 transition-all",
          sqlOpen ? "max-h-[35vh]" : "max-h-11"
        )}
      >
        <button
          type="button"
          onClick={() => setSqlOpen((v) => !v)}
          className="flex w-full shrink-0 items-center gap-3 px-3 py-2 text-left hover:bg-card/60"
        >
          <div className="flex shrink-0 items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <Database size={11} /> SQL
          </div>
          {!sqlOpen && resp.sql && (
            <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground/80">
              {resp.sql.replace(/\s+/g, " ")}
            </code>
          )}
          {resp.explainer?.explain_cost != null && (
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              cost {Math.round(resp.explainer.explain_cost)}
            </span>
          )}
          <ChevronDown
            size={14}
            className={cn(
              "shrink-0 text-muted-foreground transition-transform",
              sqlOpen && "rotate-180"
            )}
          />
        </button>
        {sqlOpen && (
          <div className="flex-1 min-h-0 overflow-auto border-t border-border/50 px-3 py-3">
            {resp.sql ? (
              <SqlPreview
                bare
                sql={resp.sql}
                appliedRules={undefined}
                cost={resp.explainer?.explain_cost ?? null}
                rows={resp.explainer?.explain_rows ?? null}
              />
            ) : (
              <div className="py-2 text-center text-xs text-muted-foreground">
                SQL не сгенерирован.
              </div>
            )}
          </div>
        )}
      </section>

            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card/40">
        <header className="flex items-center justify-between gap-2 border-b border-border/50 px-3 py-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <Sparkles size={11} /> Результат
          </div>
          {resp.rows && (
            <span className="text-[11px] text-muted-foreground">
              {resp.rows.length.toLocaleString("ru-RU")} строк ·{" "}
              {resp.columns?.length ?? 0} колонок
            </span>
          )}
        </header>
        <div className="flex-1 overflow-auto px-3 py-3">
          {resp.columns && resp.rows ? (
            <ResultChart
              bare
              columns={resp.columns}
              rows={resp.rows}
              hint={resp.chart_hint}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              Нет данных.
            </div>
          )}
        </div>
      </section>

            <section
        className={cn(
          "flex flex-col overflow-hidden rounded-lg border border-border bg-card/40 transition-all",
          explainerOpen ? "max-h-[35vh]" : "max-h-11"
        )}
      >
        <button
          type="button"
          onClick={() => setExplainerOpen((v) => !v)}
          className="flex w-full shrink-0 items-center gap-3 px-3 py-2 text-left hover:bg-card/60"
        >
          <div className="flex shrink-0 items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <ShieldCheck size={11} /> Как понял
          </div>
          {resp.explainer && (
            <div className="min-w-0 flex-1">
              <ConfidenceMeter
                bare
                value={resp.explainer.confidence}
                components={resp.explainer.components}
              />
            </div>
          )}
          {guardRules.length > 0 && (
            <Badge
              variant="success"
              className="shrink-0 text-[10px]"
              title={`Применено правил защиты: ${guardRules.length}`}
            >
              защита · {guardRules.length}
            </Badge>
          )}
          <ChevronDown
            size={14}
            className={cn(
              "shrink-0 text-muted-foreground transition-transform",
              explainerOpen && "rotate-180"
            )}
          />
        </button>
        {explainerOpen && resp.explainer && (
          <div className="flex-1 min-h-0 space-y-3 overflow-auto border-t border-border/50 px-3 py-3">
            <HowIAnswered bare explainer={resp.explainer} />
            {guardRules.length > 0 && (
              <div>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Применённые правила защиты
                </div>
                <div className="flex flex-wrap gap-1">
                  {guardRules.map((r) => (
                    <Badge
                      key={r}
                      variant="success"
                      title={tooltipGuardRule(r)}
                      className="text-[10px]"
                    >
                      {labelGuardRule(r)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
