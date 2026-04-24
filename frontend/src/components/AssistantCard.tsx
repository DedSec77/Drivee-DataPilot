import { useState } from "react";
import {
  BookmarkPlus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ResultChart } from "@/components/ResultChart";
import { SqlPreview } from "@/components/SqlPreview";
import { HowIAnswered } from "@/components/HowIAnswered";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { useConfig } from "@/config/ConfigContext";
import { labelGuardRule, tooltipGuardRule } from "@/lib/guardLabels";
import type { AskResponse } from "@/types";

function deriveHeadline(
  columns: string[] | null,
  rows: (string | number | null)[][] | null
): { value: string; label: string } | null {
  if (!columns?.length || !rows?.length) return null;

  const numericColIdx = columns.findIndex((_, i) =>
    rows.every((r) => r[i] == null || typeof r[i] === "number")
  );
  if (numericColIdx === -1) {
    return { value: rows.length.toLocaleString("ru-RU"), label: "строк" };
  }

  const colName = columns[numericColIdx];
  let total = 0;
  for (const r of rows) {
    const v = r[numericColIdx];
    if (typeof v === "number") total += v;
  }

  if (rows.length === 1) {
    const v = rows[0][numericColIdx];
    return {
      value: typeof v === "number" ? v.toLocaleString("ru-RU") : String(v ?? "—"),
      label: colName,
    };
  }
  return { value: total.toLocaleString("ru-RU"), label: `${colName} (сумма)` };
}

type Props = {
  resp: AskResponse;
  saving: boolean;
  saveDisabled: boolean;
  onSave: () => void;
};

export function AssistantCard({
  resp,
  saving,
  saveDisabled,
  onSave,
}: Props) {
  const [tab, setTab] = useState("answer");
  const { config } = useConfig();
  const accent = config.brand.accentColor;

  const headline = deriveHeadline(resp.columns, resp.rows);
  const subline =
    resp.explainer?.interpretation?.summary_ru ||
    resp.explainer?.explanation_ru ||
    "";
  const guardCount = resp.explainer?.guard_rules_applied?.length ?? 0;

  return (
    <div className="rounded-2xl border border-border bg-card/40 shadow-sm overflow-hidden">

      <div className="flex">
        <div
          className="w-[3px]"
          style={{ backgroundColor: accent }}
          aria-hidden
        />
        <div className="flex-1 p-5">
          <Tabs value={tab} onValueChange={setTab}>
            <div className="flex items-center justify-between gap-3">
              <TabsList>
                <TabsTrigger value="answer" className="gap-1.5">
                  <Sparkles size={12} /> Ответ
                </TabsTrigger>
                <TabsTrigger value="sql">SQL</TabsTrigger>
                <TabsTrigger value="explainer">Как понял</TabsTrigger>
                <TabsTrigger value="guards" className="gap-1.5">
                  <ShieldCheck size={12} />
                  Защита
                  {guardCount > 0 && (
                    <Badge
                      variant="success"
                      className="ml-0.5 px-1.5 py-0 text-[10px]"
                    >
                      {guardCount}
                    </Badge>
                  )}
                </TabsTrigger>
              </TabsList>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1 text-muted-foreground hover:text-foreground"
                onClick={onSave}
                disabled={saveDisabled}
              >
                <BookmarkPlus size={12} />
                {saving ? "..." : "Сохранить"}
              </Button>
            </div>

            <TabsContent value="answer" className="mt-4">
              {headline && (
                <div className="mb-3">
                  <div className="text-3xl font-semibold tracking-tight">
                    {headline.value}
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">
                    {headline.label}
                  </div>
                </div>
              )}
              {subline && (
                <p className="mb-4 text-sm text-foreground/85 leading-relaxed">
                  {subline}
                </p>
              )}
              {resp.columns && resp.rows && (
                <ResultChart
                  bare
                  columns={resp.columns}
                  rows={resp.rows}
                  hint={resp.chart_hint}
                />
              )}
            </TabsContent>

            <TabsContent value="sql" className="mt-4">
              {resp.sql ? (
                <SqlPreview
                  bare
                  sql={resp.sql}
                  appliedRules={resp.explainer?.guard_rules_applied}
                  cost={resp.explainer?.explain_cost ?? null}
                  rows={resp.explainer?.explain_rows ?? null}
                />
              ) : (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  SQL не сгенерирован.
                </div>
              )}
            </TabsContent>

            <TabsContent value="explainer" className="mt-4">
              {resp.explainer ? (
                <div className="space-y-4">
                  <ConfidenceMeter
                    value={resp.explainer.confidence}
                    components={resp.explainer.components}
                  />
                  <HowIAnswered bare explainer={resp.explainer} />
                </div>
              ) : (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  Нет данных для объяснения.
                </div>
              )}
            </TabsContent>

            <TabsContent value="guards" className="mt-4">
              {guardCount > 0 ? (
                <>
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Применённые правила защиты
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {resp.explainer!.guard_rules_applied.map((r) => (
                      <Badge key={r} variant="success" title={tooltipGuardRule(r)}>
                        {labelGuardRule(r)}
                      </Badge>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
                    Запрос прошёл AST-проверку, RBAC и оценку стоимости перед
                    отправкой в базу. PII-колонки маскируются на стороне UI.
                  </p>
                </>
              ) : (
                <div className="py-6 text-center text-sm text-muted-foreground">
                  Правил защиты не применено.
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
