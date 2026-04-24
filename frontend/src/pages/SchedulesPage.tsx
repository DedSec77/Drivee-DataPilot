import { useEffect, useState } from "react";
import {
  Calendar,
  Download,
  FileText,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "@/components/ui/sonner";
import {
  createSchedule,
  deleteSchedule,
  deleteScheduledRun,
  listSchedules,
  listScheduledRuns,
  listTemplates,
  patchSchedule,
  runScheduleNow,
  type ScheduleDTO,
} from "@/api";
import { useConfig } from "@/config/ConfigContext";
import type { ScheduledRun, Template } from "@/types";

export function SchedulesPage() {
  const { config } = useConfig();
  const cronPresets = config.cronPresets;
  const defaultCron = cronPresets[0]?.expr ?? "0 9 * * 1";

  const [schedules, setSchedules] = useState<ScheduleDTO[]>([]);
  const [runs, setRuns] = useState<ScheduledRun[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const [newReportId, setNewReportId] = useState<number | null>(null);
  const [newCron, setNewCron] = useState(defaultCron);
  const [newDest, setNewDest] = useState("file:///app/data/scheduled_reports");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [s, r, t] = await Promise.all([
        listSchedules(),
        listScheduledRuns(),
        listTemplates(),
      ]);
      setSchedules(s);
      setRuns(r);
      setTemplates(t);
      if (!newReportId && t.length) setNewReportId(t[0].report_id);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onCreate = async () => {
    if (!newReportId) {
      toast.error("Выберите отчёт");
      return;
    }
    if (creating) return;
    setCreating(true);
    try {
      await createSchedule({
        report_id: newReportId,
        cron_expr: newCron,
        destination: newDest,
      });
      toast.success("Расписание создано", {
        description: `cron: ${newCron} → ${newDest}`,
      });
      setCreateOpen(false);
      load();
    } catch (e: any) {
      toast.error(e.message ?? "Не удалось создать расписание");
    } finally {
      setCreating(false);
    }
  };

  const onRunNow = async (s: ScheduleDTO) => {
    if (busyId) return;
    setBusyId(s.schedule_id);
    try {
      const r = await runScheduleNow(s.schedule_id);
      toast.success("Расписание запущено", {
        description: `${r.filename} · ${r.rows} строк`,
      });
      load();
    } catch (e: any) {
      toast.error("Не удалось запустить", {
        description: e.message ?? String(e),
      });
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (s: ScheduleDTO) => {
    if (busyId) return;
    if (!window.confirm(`Удалить расписание #${s.schedule_id}?`)) return;
    setBusyId(s.schedule_id);
    try {
      await deleteSchedule(s.schedule_id);
      toast.success("Расписание удалено", {
        description: `#${s.schedule_id} (${s.cron_expr})`,
      });
      load();
    } catch (e: any) {
      toast.error("Не удалось удалить", {
        description: e.message ?? String(e),
      });
    } finally {
      setBusyId(null);
    }
  };

  const onDeleteRun = async (filename: string) => {
    if (!window.confirm(`Удалить файл «${filename}»?`)) return;
    try {
      await deleteScheduledRun(filename);
      toast.success("Файл удалён", { description: filename });
      setRuns((prev) => prev.filter((r) => r.filename !== filename));
    } catch (e: any) {
      toast.error("Не удалось удалить файл", {
        description: e.message ?? String(e),
      });
    }
  };

  const onToggleActive = async (s: ScheduleDTO) => {
    if (busyId) return;
    setBusyId(s.schedule_id);
    try {
      const next = await patchSchedule(s.schedule_id, {
        is_active: !s.is_active,
      });
      toast.success(
        next.is_active ? "Расписание возобновлено" : "Расписание на паузе",
        {
          description: `#${s.schedule_id} (${s.cron_expr})`,
        }
      );
      load();
    } catch (e: any) {
      toast.error("Не удалось обновить", {
        description: e.message ?? String(e),
      });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calendar size={16} className="text-muted-foreground" />
            Отчёты по расписанию
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Результаты пишутся в CSV в{" "}
            <code className="font-mono">/app/data/scheduled_reports</code> и
            раздаются как <code className="font-mono">/files/scheduled/…</code>.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw size={12} /> Обновить
          </Button>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm" disabled={templates.length === 0}>
                <Plus size={12} /> Новое расписание
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Создать scheduled report</DialogTitle>
                <DialogDescription>
                  Cron-выражение (Europe/Moscow). Каждый тик записывает
                  результат SQL в CSV-файл.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-3 pt-2">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    Saved report
                  </label>
                  <select
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    value={newReportId ?? ""}
                    onChange={(e) => setNewReportId(Number(e.target.value))}
                  >
                    {templates.map((t) => (
                      <option key={t.report_id} value={t.report_id}>
                        #{t.report_id} · {t.title}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    Cron expression
                  </label>
                  <Input
                    value={newCron}
                    onChange={(e) => setNewCron(e.target.value)}
                    className="mt-1 font-mono"
                  />
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {cronPresets.map((p) => (
                      <Badge
                        key={p.expr}
                        variant="outline"
                        className="cursor-pointer hover:bg-accent"
                        onClick={() => setNewCron(p.expr)}
                      >
                        {p.label}
                      </Badge>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    Destination (метка)
                  </label>
                  <Input
                    value={newDest}
                    onChange={(e) => setNewDest(e.target.value)}
                    className="mt-1 font-mono"
                  />
                </div>
              </div>

              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setCreateOpen(false)}
                  disabled={creating}
                >
                  Отмена
                </Button>
                <Button onClick={onCreate} disabled={creating}>
                  {creating ? "Создаём…" : "Создать"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Активные расписания</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">№</TableHead>
                    <TableHead>расписание (cron)</TableHead>
                    <TableHead>отчёт</TableHead>
                    <TableHead>статус</TableHead>
                    <TableHead className="w-20 text-right">действия</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {schedules.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-4">
                        Пока нет расписаний.
                      </TableCell>
                    </TableRow>
                  )}
                  {schedules.map((s) => {
                    const isBusy = busyId === s.schedule_id;
                    return (
                      <TableRow key={s.schedule_id}>
                        <TableCell className="font-mono text-xs">
                          {s.schedule_id}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {s.cron_expr}
                        </TableCell>
                        <TableCell className="text-xs">#{s.report_id}</TableCell>
                        <TableCell>
                          <Badge variant={s.is_active ? "success" : "muted"}>
                            {s.is_active ? "активно" : "пауза"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => onRunNow(s)}
                              disabled={isBusy}
                              aria-label={`Запустить расписание ${s.schedule_id}`}
                              title="Запустить сейчас"
                            >
                              <Play size={12} />
                            </Button>
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => onToggleActive(s)}
                              disabled={isBusy}
                              aria-label={
                                s.is_active
                                  ? `Приостановить расписание ${s.schedule_id}`
                                  : `Возобновить расписание ${s.schedule_id}`
                              }
                              title={s.is_active ? "Приостановить" : "Возобновить"}
                            >
                              {s.is_active ? <Pause size={12} /> : <Play size={12} />}
                            </Button>
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => onDelete(s)}
                              disabled={isBusy}
                              aria-label={`Удалить расписание ${s.schedule_id}`}
                              title="Удалить"
                            >
                              <Trash2 size={12} />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText size={14} /> Последние выгрузки (CSV на диске)
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>файл</TableHead>
                    <TableHead>создан</TableHead>
                    <TableHead className="text-right">размер</TableHead>
                    <TableHead className="w-24"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-sm text-muted-foreground py-4">
                        Ещё не было запусков. Создайте расписание и подождите тика.
                      </TableCell>
                    </TableRow>
                  )}
                  {runs.map((r) => {
                    const created = r.created_at
                      ? new Date(r.created_at)
                      : null;
                    const createdLabel =
                      created && !Number.isNaN(created.getTime())
                        ? created.toLocaleString("ru-RU", { hour12: false })
                        : "—";
                    const sizeLabel = Number.isFinite(r.size_bytes)
                      ? `${(r.size_bytes / 1024).toFixed(1)} KB`
                      : "—";
                    return (
                    <TableRow key={r.filename}>
                      <TableCell className="font-mono text-xs">
                        {r.filename}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {createdLabel}
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        {sizeLabel}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="outline"
                            size="icon"
                            asChild
                            className="h-7 w-7"
                            title="Скачать"
                          >
                            <a
                              href={r.download_url}
                              download={r.filename}
                              aria-label={`Скачать ${r.filename}`}
                            >
                              <Download size={12} />
                            </a>
                          </Button>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => onDeleteRun(r.filename)}
                            aria-label={`Удалить ${r.filename}`}
                            title="Удалить файл"
                          >
                            <Trash2 size={12} />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
