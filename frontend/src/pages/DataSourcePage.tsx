import { useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  Database,
  Loader2,
  Plug,
  Save,
  Sparkles,
  Table as TableIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/sonner";
import {
  connectDatasource,
  generateDictionary,
  getDatasourceStatus,
  introspectDatasource,
  saveDictionaryYaml,
  type DatasourceStatus,
  type SchemaInfo,
} from "@/api";

export function DataSourcePage() {
  const [status, setStatus] = useState<DatasourceStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [dsnDraft, setDsnDraft] = useState("");
  const [connecting, setConnecting] = useState(false);

  const [schema, setSchema] = useState<SchemaInfo | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);

  const [yaml, setYaml] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const reloadStatus = async () => {
    setStatusLoading(true);
    try {
      setStatus(await getDatasourceStatus());
    } catch (e: any) {
      toast.error("Не удалось получить статус БД", {
        description: e?.message ?? String(e),
      });
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    reloadStatus();
  }, []);

  const onConnect = async () => {
    if (!dsnDraft.trim() || connecting) return;
    setConnecting(true);
    try {
      const s = await connectDatasource(dsnDraft.trim());
      setStatus(s);
      const db = s.current_database ?? "?";
      const ver = s.server_version ?? "?";
      toast.success("Подключено", {
        description: `${db} · ${ver}`,
      });
      setSchema(null);
      setYaml("");
    } catch (e: any) {
      toast.error("Не удалось подключиться", {
        description: e?.message ?? String(e),
      });
    } finally {
      setConnecting(false);
    }
  };

  const onIntrospect = async () => {
    setSchemaLoading(true);
    try {
      const s = await introspectDatasource();
      setSchema(s);
      toast.success(`Найдено таблиц: ${s.tables.length}`);
    } catch (e: any) {
      toast.error("Не удалось прочитать схему", {
        description: e?.message ?? String(e),
      });
    } finally {
      setSchemaLoading(false);
    }
  };

  const onGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    try {
      const r = await generateDictionary();
      setYaml(r.yaml_text);
      toast.success("Стартовый словарь сгенерирован", {
        description: "Просмотрите ниже и сохраните, если всё ок.",
      });
    } catch (e: any) {
      toast.error("Не удалось сгенерировать словарь", {
        description: e?.message ?? String(e),
      });
    } finally {
      setGenerating(false);
    }
  };

  const onSave = async () => {
    if (!yaml.trim() || saving) return;
    setSaving(true);
    try {
      const r = await saveDictionaryYaml(yaml);
      toast.success(`Словарь применён${r.domain ? `: ${r.domain}` : ""}`, {
        description: r.path,
      });
    } catch (e: any) {
      toast.error("Не удалось сохранить словарь", {
        description: e?.message ?? String(e),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <header>
        <h1 className="text-xl font-medium tracking-tight">Источник данных</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Подключите свою Postgres-БД, посмотрите схему и попросите LLM
          собрать стартовый семантический словарь. Текущее подключение
          применяется ко всем запросам и шаблонам.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database size={14} /> Текущее подключение
          </CardTitle>
        </CardHeader>
        <CardContent>
          {statusLoading ? (
            <Skeleton className="h-12 w-full" />
          ) : status ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={status.connected ? "success" : "destructive"}>
                {status.connected ? "подключено" : "ошибка"}
              </Badge>
              {status.current_database && (
                <Badge variant="outline">db: {status.current_database}</Badge>
              )}
              {status.dialect && (
                <Badge variant="outline">диалект: {status.dialect}</Badge>
              )}
              {status.server_version && (
                <Badge variant="outline">v{status.server_version}</Badge>
              )}
              <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">
                {status.dsn_masked}
              </code>
              {status.error && (
                <div className="mt-2 flex w-full items-start gap-2 text-xs text-destructive-foreground">
                  <AlertCircle size={12} className="mt-0.5 shrink-0" />
                  <span>{status.error}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">Нет данных</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plug size={14} /> Сменить подключение
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-foreground/90">
              DSN подключения
            </span>
            <Input
              value={dsnDraft}
              onChange={(e) => setDsnDraft(e.target.value)}
              placeholder="postgresql://user:pass@host:5432/db  или  mysql://user:pass@host:3306/db"
              className="font-mono text-xs"
            />
            <span className="text-[11px] text-muted-foreground">
              Поддерживаются PostgreSQL и MySQL. SQL для MySQL транспилируется
              автоматически через sqlglot.
            </span>
          </label>
          <div className="flex items-center gap-2">
            <Button onClick={onConnect} disabled={!dsnDraft.trim() || connecting}>
              {connecting ? (
                <Loader2 size={14} className="mr-1 animate-spin" />
              ) : (
                <Plug size={14} className="mr-1" />
              )}
              Подключиться
            </Button>
            <span className="text-[11px] text-muted-foreground">
              Перед сменой убедитесь, что схема целевой БД совпадает со
              словарём. Если нет — после подключения сгенерируйте новый
              словарь ниже.
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <TableIcon size={14} /> Схема БД
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={onIntrospect}
            disabled={!status?.connected || schemaLoading}
            className="gap-1"
          >
            {schemaLoading ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <TableIcon size={12} />
            )}
            Прочитать схему
          </Button>
        </CardHeader>
        <CardContent>
          {schemaLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : schema ? (
            <SchemaSummary schema={schema} />
          ) : (
            <div className="text-sm text-muted-foreground">
              Нажмите «Прочитать схему», чтобы увидеть таблицы и колонки
              текущей БД.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Sparkles size={14} /> Сгенерировать стартовый словарь
          </CardTitle>
          <Button
            onClick={onGenerate}
            disabled={!status?.connected || generating}
            className="gap-1"
          >
            {generating ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            Сгенерировать
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-[11px] text-muted-foreground">
            LLM получит схему текущей БД и предложит YAML словарь
            (entities, facts, measures, dimensions, политики). Вы сможете
            подправить его в редакторе и сохранить.
          </p>
          <textarea
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            placeholder="# Здесь появится YAML после генерации"
            spellCheck={false}
            className="min-h-[24rem] w-full rounded-md border border-border bg-background/60 p-3 font-mono text-xs text-foreground scrollbar-thin focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="flex items-center gap-2">
            <Button
              onClick={onSave}
              disabled={!yaml.trim() || saving}
              className="gap-1"
            >
              {saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Save size={14} />
              )}
              Сохранить как активный словарь
            </Button>
            <span className="text-[11px] text-muted-foreground">
              После сохранения кэш семантики и retriever'а инвалидируется —
              следующие вопросы пойдут уже по новому словарю.
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SchemaSummary({ schema }: { schema: SchemaInfo }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline">db: {schema.database ?? "—"}</Badge>
        <Badge variant="outline">таблиц: {schema.tables.length}</Badge>
        {schema.server_version && (
          <Badge variant="outline">pg {schema.server_version}</Badge>
        )}
      </div>
      <div className="max-h-96 space-y-2 overflow-y-auto pr-2 scrollbar-thin">
        {schema.tables.map((t) => (
          <div
            key={`${t.schema}.${t.name}`}
            className="rounded-md border border-border bg-card/40 p-3 text-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium font-mono text-xs">
                {t.schema}.{t.name}
              </span>
              <div className="flex items-center gap-1.5">
                {t.estimated_rows != null && (
                  <Badge variant="outline" className="text-[10px]">
                    ~{t.estimated_rows.toLocaleString("ru-RU")} строк
                  </Badge>
                )}
                {t.foreign_keys.length > 0 && (
                  <Badge variant="outline" className="text-[10px]">
                    FK: {t.foreign_keys.length}
                  </Badge>
                )}
              </div>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-x-3 gap-y-1 text-[11px] text-muted-foreground sm:grid-cols-2 md:grid-cols-3">
              {t.columns.map((c) => (
                <div key={c.name} className="flex items-center gap-1.5 truncate">
                  {c.is_pk && (
                    <Check size={10} className="shrink-0 text-foreground" />
                  )}
                  <code className="truncate font-mono">{c.name}</code>
                  <span className="truncate opacity-70">{c.type}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
