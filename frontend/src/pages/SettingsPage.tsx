import { useCallback, useEffect, useRef, useState } from "react";
import { Database, Loader2, Plus, RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/sonner";
import {
  getAdminStats,
  resetAdminData,
  summarizePrompt,
  type AdminResetSelection,
  type AdminStats,
} from "@/api";
import { useConfig } from "@/config/ConfigContext";
import { DEFAULT_CONFIG } from "@/config/defaults";
import type {
  AppConfig,
  CronPreset,
  EmptyChip,
  EmptyStateConfig,
  RoleOption,
} from "@/config/types";
import type { UserRole } from "@/types";

export function SettingsPage() {
  const { config, updateOverrides, resetOverrides } = useConfig();

  const onReset = () => {
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        "Сбросить все локальные настройки? Дефолты вернутся из config.json или встроенных значений."
      )
    ) {
      return;
    }
    resetOverrides();
    toast.success("Настройки сброшены к дефолтам");
  };

  return (
    <div className="mx-auto w-full max-w-4xl">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-medium tracking-tight">Настройки</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Эти параметры хранятся локально (localStorage). Команда деплоя
            может задать дефолты через{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">
              public/config.json
            </code>
            ; пользовательские изменения здесь имеют приоритет.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onReset} className="gap-1">
          <RotateCcw size={12} /> Сбросить
        </Button>
      </header>

      <Tabs defaultValue="empty">
        <TabsList>
          <TabsTrigger value="empty">Стартовый экран</TabsTrigger>
          <TabsTrigger value="roles">Роли</TabsTrigger>
          <TabsTrigger value="cron">Расписания</TabsTrigger>
          <TabsTrigger value="limits">Лимиты</TabsTrigger>
          <TabsTrigger value="api">API</TabsTrigger>
          <TabsTrigger value="data">Данные</TabsTrigger>
        </TabsList>

        <TabsContent value="empty" className="mt-4">
          <EmptyStateForm config={config} onChange={updateOverrides} />
        </TabsContent>
        <TabsContent value="roles" className="mt-4">
          <RolesForm config={config} onChange={updateOverrides} />
        </TabsContent>
        <TabsContent value="cron" className="mt-4">
          <CronForm config={config} onChange={updateOverrides} />
        </TabsContent>
        <TabsContent value="limits" className="mt-4">
          <LimitsForm config={config} onChange={updateOverrides} />
        </TabsContent>
        <TabsContent value="api" className="mt-4">
          <ApiForm config={config} onChange={updateOverrides} />
        </TabsContent>
        <TabsContent value="data" className="mt-4">
          <DataResetForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}

type FormProps = {
  config: AppConfig;
  onChange: (patch: Partial<AppConfig>) => void;
};

const AUTO_LABEL_DEBOUNCE_MS = 1000;

function EmptyStateForm({ config, onChange }: FormProps) {
  const e = config.emptyState;
  const setTitle = (title: string) =>
    onChange({ emptyState: { ...e, title } });
  const setChips = (chips: EmptyChip[]) =>
    onChange({ emptyState: { ...e, chips } });

  const addChip = () =>
    setChips([...e.chips, { icon: "Sparkles", label: "", prompt: "" }]);
  const updateChip = (idx: number, patch: Partial<EmptyChip>) =>
    setChips(e.chips.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  const removeChip = (idx: number) =>
    setChips(e.chips.filter((_, i) => i !== idx));

  const eRef = useRef<EmptyStateConfig>(e);
  eRef.current = e;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const lastGeneratedFor = useRef<Map<number, string>>(new Map());
  const [autoBusy, setAutoBusy] = useState<Set<number>>(new Set());

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    e.chips.forEach((chip, idx) => {
      const prompt = chip.prompt.trim();
      const label = chip.label.trim();
      if (!prompt) return;
      if (label) return;
      if (lastGeneratedFor.current.get(idx) === prompt) return;

      const t = setTimeout(async () => {
        const fresh = eRef.current.chips[idx];
        if (!fresh) return;
        const freshPrompt = fresh.prompt.trim();
        if (!freshPrompt) return;
        if (fresh.label.trim()) return;

        lastGeneratedFor.current.set(idx, freshPrompt);
        setAutoBusy((s) => {
          const next = new Set(s);
          next.add(idx);
          return next;
        });

        try {
          const { label: generated } = await summarizePrompt(freshPrompt);
          const latest = eRef.current.chips[idx];
          if (!latest) return;
          if (latest.label.trim()) return;
          if (latest.prompt.trim() !== freshPrompt) return;

          const nextChips = eRef.current.chips.map((c, j) =>
            j === idx ? { ...c, label: generated } : c
          );
          onChangeRef.current({
            emptyState: { ...eRef.current, chips: nextChips },
          });
        } catch (err: any) {
          toast.error("Авто-подпись не удалась", {
            description: err?.message ?? String(err),
          });
          lastGeneratedFor.current.delete(idx);
        } finally {
          setAutoBusy((s) => {
            const next = new Set(s);
            next.delete(idx);
            return next;
          });
        }
      }, AUTO_LABEL_DEBOUNCE_MS);

      timers.push(t);
    });

    return () => {
      timers.forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e.chips]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Заголовок</CardTitle>
        </CardHeader>
        <CardContent>
          <Field label="Текст в пустом состоянии">
            <Input value={e.title} onChange={(ev) => setTitle(ev.target.value)} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Chip-кнопки с примерами</CardTitle>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Введите полный вопрос — короткая подпись подтянется
              автоматически через секунду. Если впишете подпись сами —
              авто-генерация отступает.
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={addChip} className="gap-1">
            <Plus size={12} /> Добавить
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {e.chips.length === 0 ? (
            <Empty hint="Нет чипов. Добавьте, чтобы предложить пользователю стартовые вопросы." />
          ) : (
            e.chips.map((c, i) => {
              const busy = autoBusy.has(i);
              return (
                <div
                  key={i}
                  className="grid gap-2 rounded-md border border-border bg-card/40 p-3 md:grid-cols-[12rem,1fr,auto]"
                >
                  <Input
                    value={c.label}
                    onChange={(ev) => updateChip(i, { label: ev.target.value })}
                    placeholder={busy ? "Генерируем…" : "Подпись"}
                    disabled={busy}
                  />
                  <Input
                    value={c.prompt}
                    onChange={(ev) => updateChip(i, { prompt: ev.target.value })}
                    placeholder="Полный вопрос, который отправится"
                  />
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => removeChip(i)}
                    aria-label="Удалить"
                    className="h-9 w-9 text-muted-foreground hover:text-destructive-foreground"
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RolesForm({ config, onChange }: FormProps) {
  const roles = config.roles;
  const set = (next: RoleOption[]) => onChange({ roles: next });

  const update = (idx: number, patch: Partial<RoleOption>) =>
    set(roles.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const remove = (idx: number) => set(roles.filter((_, i) => i !== idx));
  const setDefault = (idx: number) =>
    set(roles.map((r, i) => ({ ...r, isDefault: i === idx })));
  const add = () =>
    set([
      ...roles,
      {
        id: "business_user",
        label: "Новая роль",
        hint: "",
        icon: "User",
      },
    ]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Роли</CardTitle>
        <Button size="sm" variant="outline" onClick={add} className="gap-1">
          <Plus size={12} /> Добавить
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          ID роли должен совпадать с тем, что распознаёт backend (
          <code className="font-mono">business_user</code> или{" "}
          <code className="font-mono">analyst</code>). Лейбл и подсказка —
          для UI.
        </p>
        {roles.map((r, i) => (
          <div
            key={i}
            className="grid gap-2 rounded-md border border-border bg-card/40 p-3 md:grid-cols-[8rem,1fr,1fr,7rem,auto,auto]"
          >
            <select
              value={r.id}
              onChange={(ev) =>
                update(i, { id: ev.target.value as UserRole })
              }
              className="rounded-md border border-input bg-background px-2 py-1 text-sm"
            >
              <option value="business_user">business_user</option>
              <option value="analyst">analyst</option>
            </select>
            <Input
              value={r.label}
              onChange={(ev) => update(i, { label: ev.target.value })}
              placeholder="Менеджер"
            />
            <Input
              value={r.hint}
              onChange={(ev) => update(i, { hint: ev.target.value })}
              placeholder="что видит / умеет"
            />
            <Input
              value={r.icon ?? ""}
              onChange={(ev) => update(i, { icon: ev.target.value })}
              placeholder="Lucide icon"
              className="font-mono text-xs"
            />
            <button
              type="button"
              onClick={() => setDefault(i)}
              className="text-xs text-muted-foreground hover:text-foreground"
              title="Использовать как роль по умолчанию"
            >
              {r.isDefault ? (
                <Badge variant="success">по умолчанию</Badge>
              ) : (
                "сделать дефолтом"
              )}
            </button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => remove(i)}
              aria-label="Удалить"
              className="h-9 w-9 text-muted-foreground hover:text-destructive-foreground"
            >
              <Trash2 size={14} />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function CronForm({ config, onChange }: FormProps) {
  const presets = config.cronPresets;
  const set = (next: CronPreset[]) => onChange({ cronPresets: next });

  const update = (idx: number, patch: Partial<CronPreset>) =>
    set(presets.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  const remove = (idx: number) => set(presets.filter((_, i) => i !== idx));
  const add = () =>
    set([...presets, { label: "Новый пресет", expr: "* * * * *" }]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Cron-пресеты для расписаний</CardTitle>
        <Button size="sm" variant="outline" onClick={add} className="gap-1">
          <Plus size={12} /> Добавить
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {presets.map((p, i) => (
          <div
            key={i}
            className="grid gap-2 rounded-md border border-border bg-card/40 p-3 md:grid-cols-[1fr,12rem,auto]"
          >
            <Input
              value={p.label}
              onChange={(ev) => update(i, { label: ev.target.value })}
              placeholder="Каждый понедельник 9:00"
            />
            <Input
              value={p.expr}
              onChange={(ev) => update(i, { expr: ev.target.value })}
              className="font-mono"
              placeholder="0 9 * * 1"
            />
            <Button
              size="icon"
              variant="ghost"
              onClick={() => remove(i)}
              aria-label="Удалить"
              className="h-9 w-9 text-muted-foreground hover:text-destructive-foreground"
            >
              <Trash2 size={14} />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function LimitsForm({ config, onChange }: FormProps) {
  const l = config.limits;
  const set = (patch: Partial<typeof l>) =>
    onChange({ limits: { ...l, ...patch } });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Лимиты и UI</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-3">
        <Field
          label="Размер истории чата (ходов)"
          hint={`по умолчанию ${DEFAULT_CONFIG.limits.historyLimit}`}
        >
          <Input
            type="number"
            min={0}
            max={50}
            value={l.historyLimit}
            onChange={(ev) =>
              set({ historyLimit: Math.max(0, Number(ev.target.value) || 0) })
            }
          />
        </Field>
        <Field
          label="Owner для сохранённых шаблонов"
          hint={`backend поле owner`}
        >
          <Input
            value={l.templateOwner}
            onChange={(ev) => set({ templateOwner: ev.target.value })}
          />
        </Field>
        <Field
          label="Масштаб UI, %"
          hint={`по умолчанию ${DEFAULT_CONFIG.limits.uiScalePct}%`}
        >
          <Input
            type="number"
            min={50}
            max={300}
            step={5}
            value={l.uiScalePct}
            onChange={(ev) =>
              set({
                uiScalePct: Math.max(
                  50,
                  Math.min(300, Number(ev.target.value) || 100)
                ),
              })
            }
          />
        </Field>
      </CardContent>
    </Card>
  );
}

function ApiForm({ config, onChange }: FormProps) {
  const a = config.api;
  const [draft, setDraft] = useState(a.baseUrl);
  return (
    <Card>
      <CardHeader>
        <CardTitle>API backend</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Field
          label="URL backend"
          hint="любой OpenAPI-совместимый endpoint Drivee DataPilot"
        >
          <div className="flex gap-2">
            <Input
              value={draft}
              onChange={(ev) => setDraft(ev.target.value)}
              placeholder="http://localhost:8000"
              className="font-mono"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onChange({ api: { ...a, baseUrl: draft.trim() || a.baseUrl } });
                toast.success("Backend URL обновлён");
              }}
            >
              Применить
            </Button>
          </div>
        </Field>
        <p className="text-[11px] text-muted-foreground">
          Изменение применяется сразу для всех последующих запросов. Активные
          контейнеры backend для нового URL должны быть подняты отдельно.
        </p>
      </CardContent>
    </Card>
  );
}

const RESET_ROWS: {
  key: keyof AdminStats;
  label: string;
  hint: string;
  destructive?: boolean;
}[] = [
  {
    key: "logs",
    label: "Журнал запросов",
    hint: "История всех вопросов и SQL — то, что видно на странице «Анализ → Журнал»",
  },
  {
    key: "templates",
    label: "Сохранённые шаблоны",
    hint: "Включая аппрувленные. Удаление каскадно снесёт связанные расписания.",
  },
  {
    key: "schedules",
    label: "Расписания",
    hint: "Сами cron-правила. Файлы прошлых выгрузок на диске не трогаются.",
  },
  {
    key: "trips",
    label: "Поездки (демо-данные)",
    hint: "Таблица fct_trips. После сброса задайте вопрос — данных не будет, нужен повторный seed.",
    destructive: true,
  },
];

function DataResetForm() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<Record<keyof AdminStats, boolean>>({
    logs: false,
    templates: false,
    schedules: false,
    trips: false,
  });

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setStats(await getAdminStats());
    } catch (e: any) {
      toast.error("Не удалось получить статистику", {
        description: e?.message ?? String(e),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const toggle = (k: keyof AdminStats) =>
    setPicked((p) => ({ ...p, [k]: !p[k] }));

  const selectedKeys = (Object.keys(picked) as (keyof AdminStats)[]).filter(
    (k) => picked[k]
  );
  const hasSelection = selectedKeys.length > 0;

  const onReset = async () => {
    if (!hasSelection) return;
    const labels = selectedKeys
      .map((k) => RESET_ROWS.find((r) => r.key === k)?.label ?? k)
      .join(", ");
    const total = stats
      ? selectedKeys.reduce((sum, k) => sum + (stats[k] ?? 0), 0)
      : 0;
    if (
      !window.confirm(
        `Удалить безвозвратно ${total} строк из таблиц: ${labels}?\n\n` +
          `Это действие нельзя отменить.`
      )
    ) {
      return;
    }

    setBusy(true);
    try {
      const result = await resetAdminData(picked as AdminResetSelection);
      const sum = Object.values(result.deleted).reduce(
        (a, b) => a + (b ?? 0),
        0
      );
      toast.success(`Удалено ${sum} строк`, {
        description: `Очищено: ${result.tables.join(", ")}`,
      });
      setPicked({
        logs: false,
        templates: false,
        schedules: false,
        trips: false,
      });
      await reload();
    } catch (e: any) {
      toast.error("Сброс не удался", {
        description: e?.message ?? String(e),
      });
    } finally {
      setBusy(false);
    }
  };

  const onSelectAll = () =>
    setPicked({ logs: true, templates: true, schedules: true, trips: true });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Database size={14} className="text-muted-foreground" />
            Локальная БД (PostgreSQL)
          </CardTitle>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Один клик чистит выбранные таблицы Postgres через
            <code className="ml-1 rounded bg-muted px-1 font-mono text-[10px]">
              TRUNCATE … RESTART IDENTITY CASCADE
            </code>
            . Удалённые строки не восстановить.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={reload}
          disabled={loading || busy}
          className="gap-1"
        >
          <RotateCcw size={12} className={loading ? "animate-spin" : ""} />
          Обновить
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="w-10 px-3 py-2 text-left"></th>
                <th className="px-3 py-2 text-left font-medium">Таблица</th>
                <th className="w-28 px-3 py-2 text-right font-medium">
                  Строк сейчас
                </th>
              </tr>
            </thead>
            <tbody>
              {RESET_ROWS.map((r) => {
                const count = stats?.[r.key];
                const checked = picked[r.key];
                return (
                  <tr
                    key={r.key}
                    className="border-t border-border hover:bg-muted/20"
                  >
                    <td className="px-3 py-2 align-top">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(r.key)}
                        disabled={busy}
                        className="h-4 w-4 cursor-pointer accent-primary"
                        aria-label={`Выбрать ${r.label}`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{r.label}</span>
                        {r.destructive && (
                          <Badge variant="destructive" className="text-[10px]">
                            демо-данные
                          </Badge>
                        )}
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        {r.hint}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {loading ? (
                        <span className="text-muted-foreground">…</span>
                      ) : count != null ? (
                        count.toLocaleString("ru-RU")
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onSelectAll}
            disabled={busy}
            className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:opacity-40"
          >
            Выбрать всё
          </button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onReset}
            disabled={!hasSelection || busy}
            className="gap-1.5"
          >
            {busy ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                Удаляю…
              </>
            ) : (
              <>
                <Trash2 size={12} />
                Сбросить выбранное
              </>
            )}
          </Button>
        </div>

        <p className="text-[11px] text-muted-foreground">
          После сброса <span className="font-medium">fct_trips</span> залить
          синтетику снова можно командой:{" "}
          <code className="rounded bg-muted px-1 font-mono text-[10px]">
            docker compose exec -T backend python -m app.db.seed_from_tlc
            --months 1 --sample 10000
          </code>
        </p>
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-foreground/90">{label}</span>
      {children}
      {hint && (
        <span className="text-[10px] text-muted-foreground">{hint}</span>
      )}
    </label>
  );
}

function Empty({ hint }: { hint: string }) {
  return (
    <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
      {hint}
    </div>
  );
}
