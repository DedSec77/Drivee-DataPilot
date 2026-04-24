import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as LucideIcons from "lucide-react";
import {
  AlertTriangle,
  ArrowUp,
  CircleHelp,
  Plus,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useConfig } from "@/config/ConfigContext";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { SqlPreview } from "@/components/SqlPreview";
import { AssistantCard } from "@/components/AssistantCard";
import { AnswerSkeleton } from "@/components/AnswerSkeleton";
import { ThinkingTrace } from "@/components/ThinkingTrace";
import { WorkspacePane } from "@/components/WorkspacePane";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { DataSourcePage } from "@/pages/DataSourcePage";
import { DictionaryPage } from "@/pages/DictionaryPage";
import { SchedulesPage } from "@/pages/SchedulesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TemplatesPage } from "@/pages/TemplatesPage";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Toaster, toast } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  approveTemplate,
  askStream,
  deleteTemplate,
  executeSql,
  listTemplates,
  saveTemplate,
} from "@/api";
import type {
  AskResponse,
  ChatMessage,
  ChatTurn,
  Conversation,
  Route,
  StageEvent,
  Template,
  UserRole,
} from "@/types";

const SIDEBAR_STORAGE_KEY = "drivee.sidebar.open";
const CONVERSATIONS_STORAGE_KEY = "drivee.conversations.v1";
const ACTIVE_CONVERSATION_STORAGE_KEY = "drivee.conversations.active";
const ROLE_STORAGE_KEY = "drivee.role";

function lucideByName(name: string | undefined): LucideIcon {
  if (!name) return Sparkles;
  const Icon = (LucideIcons as unknown as Record<string, LucideIcon | undefined>)[name];
  return Icon ?? Sparkles;
}

function deriveConversationTitle(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "Новый чат";
  const t = (firstUser as Extract<ChatMessage, { role: "user" }>).text.trim();
  return t.length > 60 ? `${t.slice(0, 57).trimEnd()}…` : t;
}

let _convIdCounter = 0;
const newConversationId = () =>
  `c_${Date.now().toString(36)}_${(_convIdCounter++).toString(36)}`;

function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as Conversation[];
  } catch {
    return [];
  }
}

function loadActiveConversationId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY);
}

function loadRole(): UserRole {
  if (typeof window === "undefined") return "business_user";
  const stored = window.localStorage.getItem(ROLE_STORAGE_KEY);
  return stored === "analyst" ? "analyst" : "business_user";
}

let _msgIdCounter = 0;
const newMessageId = () =>
  `m_${Date.now().toString(36)}_${(_msgIdCounter++).toString(36)}`;

function assistantSummary(resp: AskResponse): string {
  if (resp.kind === "answer") {
    const interp = resp.explainer?.interpretation?.summary_ru;
    const expl = resp.explainer?.explanation_ru;
    const rowCount = resp.rows?.length ?? 0;
    const head = expl || interp || "";
    const tail =
      rowCount > 0 ? ` (получено строк: ${rowCount})` : " (пустой результат)";
    return (head + tail).trim();
  }
  if (resp.kind === "clarify") {
    return resp.clarify_question
      ? `Уточняющий вопрос: ${resp.clarify_question}`
      : "Уточняющий вопрос";
  }
  if (resp.kind === "error") {
    return resp.error
      ? `Запрос не выполнен (${resp.error.code}): ${resp.error.hint_ru}`
      : "Запрос не выполнен";
  }
  return "";
}

function buildChatHistory(
  messages: ChatMessage[],
  limit: number
): ChatTurn[] {
  const turns: ChatTurn[] = [];
  for (const m of messages) {
    if (m.role === "user") continue;
    if (!m.resp) continue;
    const turn: ChatTurn = {
      question: m.question,
      kind: m.resp.kind,
    };
    const summary = assistantSummary(m.resp);
    if (summary) turn.summary = summary;
    if (m.resp.sql) turn.sql = m.resp.sql;
    turns.push(turn);
  }
  return turns.slice(-limit);
}

function historySignature(history: ChatTurn[]): string {
  if (history.length === 0) return "";
  return history.map((t) => `${t.kind ?? "?"}:${t.question}`).join("||");
}

export default function App() {
  const { config } = useConfig();
  const HISTORY_LIMIT = config.limits.historyLimit;
  const [route, setRoute] = useState<Route>("ask");
  const [busy, setBusy] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (stored !== null) return stored === "1";
    return window.innerWidth >= 768;
  });
  const [visited, setVisited] = useState<Set<Route>>(() => new Set(["ask"]));

  const [conversations, setConversations] = useState<Conversation[]>(() => {
    const stored = loadConversations();
    if (stored.length > 0) return stored;
    const initial: Conversation = {
      id: newConversationId(),
      title: "Новый чат",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    };
    return [initial];
  });
  const [activeConversationId, setActiveConversationId] = useState<string>(
    () => {
      const stored = loadActiveConversationId();
      const all = loadConversations();
      if (stored && all.some((c) => c.id === stored)) return stored;
      return all[0]?.id ?? "";
    }
  );

  const [role, setRole] = useState<UserRole>(() => loadRole());

  const answerCache = useRef<Map<string, AskResponse>>(new Map());

  useEffect(() => {
    if (!conversations.find((c) => c.id === activeConversationId)) {
      const next = conversations[0]?.id ?? "";
      setActiveConversationId(next);
    }
  }, [conversations, activeConversationId]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        CONVERSATIONS_STORAGE_KEY,
        JSON.stringify(conversations)
      );
    } catch {}
  }, [conversations]);

  useEffect(() => {
    if (activeConversationId) {
      window.localStorage.setItem(
        ACTIVE_CONVERSATION_STORAGE_KEY,
        activeConversationId
      );
    }
  }, [activeConversationId]);

  useEffect(() => {
    window.localStorage.setItem(ROLE_STORAGE_KEY, role);
  }, [role]);

  const messages: ChatMessage[] = useMemo(() => {
    return (
      conversations.find((c) => c.id === activeConversationId)?.messages ?? []
    );
  }, [conversations, activeConversationId]);

  const setMessages = (
    updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])
  ) => {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== activeConversationId) return c;
        const next =
          typeof updater === "function"
            ? (updater as (p: ChatMessage[]) => ChatMessage[])(c.messages)
            : updater;
        return {
          ...c,
          messages: next,
          title: deriveConversationTitle(next),
          updatedAt: Date.now(),
        };
      })
    );
  };

  useEffect(() => {
    setVisited((prev) => {
      if (prev.has(route)) return prev;
      const next = new Set(prev);
      next.add(route);
      return next;
    });
  }, [route]);

  const reloadTemplates = () =>
    listTemplates().then(setTemplates).catch(() => void 0);

  useEffect(() => {
    reloadTemplates();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setSidebarOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, []);

  const latestAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m.role === "assistant" && !m.pending && m.resp) return m;
    }
    return null;
  }, [messages]);

  const sortedConversations = useMemo(
    () => [...conversations].sort((a, b) => b.updatedAt - a.updatedAt),
    [conversations]
  );

  const onAsk = async (q: string) => {
    setRoute("ask");
    const trimmed = q.trim();
    if (!trimmed || busy) return;

    setBusy(true);

    const history = buildChatHistory(messages, HISTORY_LIMIT);
    const key = `${historySignature(history)}::${trimmed.toLowerCase()}`;
    const cached = answerCache.current.get(key);

    const userMsg: ChatMessage = {
      id: newMessageId(),
      role: "user",
      text: trimmed,
    };
    const assistantId = newMessageId();
    const placeholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      question: trimmed,
      resp: null,
      pending: true,
      fromCache: !!(cached && cached.kind === "answer" && cached.sql),
      stages: [],
    };
    setMessages((prev) => [...prev, userMsg, placeholder]);

    const finishAssistant = (patch: Partial<Extract<ChatMessage, { role: "assistant" }>>) =>
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.role === "assistant" ? { ...m, ...patch } : m
        )
      );

    const appendStage = (event: StageEvent) =>
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId || m.role !== "assistant") return m;
          const stages = [...(m.stages ?? []), event];
          return { ...m, stages };
        })
      );

    try {
      if (cached && cached.kind === "answer" && cached.sql) {
        try {
          const fresh = await executeSql(cached.sql, role);
          const merged: AskResponse = {
            ...cached,
            sql: fresh.sql,
            columns: fresh.columns,
            rows: fresh.rows,
            explainer: cached.explainer
              ? {
                  ...cached.explainer,
                  guard_rules_applied: fresh.applied_rules,
                  explain_cost: fresh.est_cost,
                  explain_rows: fresh.est_rows,
                }
              : cached.explainer,
          };
          finishAssistant({ resp: merged, pending: false, stages: [] });
          answerCache.current.set(key, merged);
          toast.success("Запустили тот же SQL заново", {
            description: `Свежие ${fresh.rows.length} строк`,
          });
          return;
        } catch (e: any) {
          toast.info("Не удалось переиспользовать кэш, спрашиваем заново", {
            description: e.message ?? String(e),
          });
          finishAssistant({ fromCache: false });
        }
      }

      const r = await askStream(
        trimmed,
        { role, chatHistory: history.length > 0 ? history : undefined },
        appendStage
      );
      finishAssistant({ resp: r, pending: false, fromCache: false });
      if (r.kind === "answer") {
        answerCache.current.set(key, r);
      }
      if (r.kind === "error" && r.error) {
        toast.error(`Защита сработала: ${r.error.code}`, {
          description: r.error.hint_ru,
        });
      } else if (r.kind === "clarify") {
        toast.info("Нужно уточнение", {
          description: r.clarify_question ?? undefined,
        });
      }
    } catch (e: any) {
      toast.error("Ошибка запроса", { description: e.message ?? String(e) });
      finishAssistant({
        resp: {
          kind: "error",
          sql: null,
          columns: null,
          rows: null,
          clarify_question: null,
          clarify_options: null,
          explainer: null,
          chart_hint: null,
          error: { code: "NETWORK", hint_ru: e?.message ?? String(e) },
        },
        pending: false,
        fromCache: false,
        stages: [],
      });
    } finally {
      setBusy(false);
    }
  };

  const onNewChat = () => {
    if (busy) return;

    setConversations((prev) => {
      const active = prev.find((c) => c.id === activeConversationId);
      if (active && active.messages.length === 0) return prev;

      const fresh: Conversation = {
        id: newConversationId(),
        title: "Новый чат",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      };
      const cleaned = prev.filter((c) => c.messages.length > 0);
      const next = [fresh, ...cleaned];
      setActiveConversationId(fresh.id);
      return next;
    });
  };

  const onPickConversation = (id: string) => {
    if (busy) return;
    setActiveConversationId(id);
  };

  const onDeleteConversation = (id: string) => {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      if (next.length === 0) {
        const fresh: Conversation = {
          id: newConversationId(),
          title: "Новый чат",
          createdAt: Date.now(),
          updatedAt: Date.now(),
          messages: [],
        };
        setActiveConversationId(fresh.id);
        return [fresh];
      }
      if (id === activeConversationId) {
        setActiveConversationId(next[0].id);
      }
      return next;
    });
  };

  const onRunTemplate = async (template: Template) => {
    if (busy) return;
    setRoute("ask");
    setBusy(true);

    const userText = template.nl_question || template.title;
    const userMsg: ChatMessage = {
      id: newMessageId(),
      role: "user",
      text: userText,
    };
    const assistantId = newMessageId();
    const placeholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      question: userText,
      resp: null,
      pending: true,
      fromCache: true,
    };
    setMessages((prev) => [...prev, userMsg, placeholder]);

    const finishAssistant = (
      patch: Partial<Extract<ChatMessage, { role: "assistant" }>>
    ) =>
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.role === "assistant" ? { ...m, ...patch } : m
        )
      );

    try {
      const fresh = await executeSql(template.sql_text, role);
      const chartHint =
        (template.chart_type as AskResponse["chart_hint"] | null) ?? "table";
      const resp: AskResponse = {
        kind: "answer",
        sql: fresh.sql,
        columns: fresh.columns,
        rows: fresh.rows,
        clarify_question: null,
        clarify_options: null,
        error: null,
        chart_hint: chartHint,
        explainer: {
          confidence: template.is_approved ? 1.0 : 0.9,
          components: { template: 1.0 },
          used_metrics: [],
          used_dimensions: [],
          time_range: null,
          explanation_ru: `Запущен сохранённый шаблон «${template.title}». SQL выполнен напрямую, без обращения к LLM.`,
          guard_rules_applied: fresh.applied_rules,
          explain_cost: fresh.est_cost,
          explain_rows: fresh.est_rows,
          interpretation: null,
        },
      };
      finishAssistant({ resp, pending: false, fromCache: false });
      toast.success(`Шаблон выполнен: ${template.title}`, {
        description: `Получено ${fresh.rows.length} строк`,
      });
    } catch (e: any) {
      finishAssistant({
        resp: {
          kind: "error",
          sql: template.sql_text,
          columns: null,
          rows: null,
          clarify_question: null,
          clarify_options: null,
          explainer: null,
          chart_hint: null,
          error: {
            code: "TEMPLATE_EXEC",
            hint_ru: e?.message ?? String(e),
          },
        },
        pending: false,
        fromCache: false,
      });
      toast.error("Не удалось выполнить шаблон", {
        description: e?.message ?? String(e),
      });
    } finally {
      setBusy(false);
    }
  };

  const [saving, setSaving] = useState(false);

  const onSaveCurrent = async () => {
    if (
      !latestAssistant?.resp?.sql ||
      !latestAssistant.question ||
      saving
    )
      return;
    setSaving(true);
    try {
      await saveTemplate({
        owner: config.limits.templateOwner,
        title: latestAssistant.question.slice(0, 80),
        nl_question: latestAssistant.question,
        sql_text: latestAssistant.resp.sql,
        chart_type: latestAssistant.resp.chart_hint ?? "table",
      });
      toast.success("Шаблон сохранён");
      reloadTemplates();
    } catch (e: any) {
      toast.error("Не удалось сохранить", {
        description: e.message ?? String(e),
      });
    } finally {
      setSaving(false);
    }
  };

  const onApprove = async (t: Template) => {
    try {
      await approveTemplate(t.report_id);
      toast.success("Шаблон одобрен", {
        description:
          "Добавлен в индекс few-shot. Похожие запросы теперь отвечаются лучше.",
      });
      reloadTemplates();
    } catch (e: any) {
      toast.error("Не удалось одобрить", {
        description: e.message ?? String(e),
      });
    }
  };

  const onDelete = async (t: Template) => {
    try {
      await deleteTemplate(t.report_id);
      toast.success("Шаблон удалён", {
        description: t.title,
      });
      reloadTemplates();
    } catch (e: any) {
      toast.error("Не удалось удалить", {
        description: e.message ?? String(e),
      });
    }
  };

  return (
    <TooltipProvider>
      <div className="flex h-screen overflow-hidden bg-background text-foreground">
        <Sidebar
          current={route}
          onNavigate={setRoute}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          conversations={sortedConversations}
          activeConversationId={activeConversationId}
          onPickConversation={onPickConversation}
          onNewChat={onNewChat}
          onDeleteConversation={onDeleteConversation}
          busy={busy}
          role={role}
          onChangeRole={setRole}
        />

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Topbar
            sidebarOpen={sidebarOpen}
            onToggleSidebar={() => setSidebarOpen((o) => !o)}
            route={route}
          />
          <div className="flex-1 overflow-y-scroll scrollbar-thin scrollbar-stable">
            <div className="container max-w-7xl py-6 px-6">
              <RoutePane active={route === "ask"}>
                <AskPage
                  busy={busy}
                  messages={messages}
                  saving={saving}
                  onAsk={onAsk}
                  onNewChat={onNewChat}
                  onSaveCurrent={onSaveCurrent}
                />
              </RoutePane>
              {visited.has("templates") && (
                <RoutePane active={route === "templates"}>
                  <TemplatesPage
                    templates={templates}
                    onPick={onRunTemplate}
                    onApprove={onApprove}
                    onDelete={onDelete}
                  />
                </RoutePane>
              )}
              {visited.has("schedules") && (
                <RoutePane active={route === "schedules"}>
                  <SchedulesPage />
                </RoutePane>
              )}
              {visited.has("dictionary") && (
                <RoutePane active={route === "dictionary"}>
                  <DictionaryPage />
                </RoutePane>
              )}
              {visited.has("datasource") && (
                <RoutePane active={route === "datasource"}>
                  <DataSourcePage />
                </RoutePane>
              )}
              {visited.has("analysis") && (
                <RoutePane active={route === "analysis"}>
                  <AnalysisPage />
                </RoutePane>
              )}
              {visited.has("settings") && (
                <RoutePane active={route === "settings"}>
                  <SettingsPage />
                </RoutePane>
              )}
            </div>
          </div>
        </main>

        <Toaster />
      </div>
    </TooltipProvider>
  );
}

function AskPage({
  busy,
  messages,
  saving,
  onAsk,
  onNewChat,
  onSaveCurrent,
}: {
  busy: boolean;
  messages: ChatMessage[];
  saving: boolean;
  onAsk: (q: string) => void;
  onNewChat: () => void;
  onSaveCurrent: () => void;
}) {
  const isIdle = messages.length === 0;
  const bottomRef = useRef<HTMLDivElement>(null);

  const latestAssistantId = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m.role === "assistant" && !m.pending && m.resp?.kind === "answer") {
        return m.id;
      }
    }
    return null;
  })();

  useEffect(() => {
    if (messages.length === 0) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const latestAnswerMsg = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (
        m.role === "assistant" &&
        !m.pending &&
        m.resp?.kind === "answer" &&
        m.resp.sql
      ) {
        return m;
      }
    }
    return null;
  })();

  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null);
  useEffect(() => {
    if (selectedAnswerId && latestAnswerMsg?.id !== selectedAnswerId) {
      const stillExists = messages.some(
        (m) => m.role === "assistant" && m.id === selectedAnswerId
      );
      if (!stillExists) setSelectedAnswerId(null);
    }
  }, [messages, selectedAnswerId, latestAnswerMsg?.id]);

  const activeAnswerMsg = selectedAnswerId
    ? (messages.find(
        (m) => m.role === "assistant" && m.id === selectedAnswerId
      ) as Extract<ChatMessage, { role: "assistant" }> | undefined) ??
      latestAnswerMsg
    : latestAnswerMsg;

  const historyCount = messages.filter(
    (m) => m.role === "assistant" && !m.pending && !!m.resp
  ).length;

  if (isIdle) {
    return (
      <div
        className="mx-auto flex w-full max-w-3xl flex-col"
        style={{ minHeight: "calc(100vh - 6rem)" }}
      >
        <div className="flex-1">
          <EmptyHeader onPick={onAsk} />
        </div>
        <div className="sticky bottom-0 z-10 mt-4 bg-gradient-to-t from-background via-background to-transparent pb-2 pt-4">
          <ChatInputBar busy={busy} onSend={onAsk} historyCount={0} />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex w-full gap-3"
      style={{ height: "calc(100vh - 6rem)" }}
    >
            <aside className="flex w-full max-w-md shrink-0 flex-col rounded-xl border border-border bg-card/30 lg:w-[320px]">
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-2">
          <div className="text-[11px] text-muted-foreground">
            Диалог · {messages.filter((m) => m.role === "user").length}{" "}
            {pluralizeRu(
              messages.filter((m) => m.role === "user").length,
              ["вопрос", "вопроса", "вопросов"]
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onNewChat}
            disabled={busy}
            className="h-7 gap-1 text-xs"
          >
            <Plus size={11} /> Новый
          </Button>
        </div>

        <div className="flex-1 space-y-3 overflow-auto px-4 py-4">
          {messages.map((m) =>
            m.role === "user" ? (
              <UserQuestionBubble key={m.id} text={m.text} />
            ) : (
              <AssistantTurn
                key={m.id}
                message={m}
                onAsk={onAsk}
                isLatestAnswer={m.id === latestAssistantId}
                saving={saving}
                onSave={onSaveCurrent}
                compact
                isActive={m.id === activeAnswerMsg?.id}
                onSelect={() =>
                  setSelectedAnswerId(
                    m.id === latestAnswerMsg?.id ? null : m.id
                  )
                }
              />
            )
          )}
          <div ref={bottomRef} aria-hidden="true" />
        </div>

        <div className="border-t border-border/60 bg-gradient-to-t from-background via-background to-transparent px-3 pb-3 pt-3">
          <ChatInputBar busy={busy} onSend={onAsk} historyCount={historyCount} />
        </div>
      </aside>

            <main className="flex min-w-0 flex-1 flex-col">
        {activeAnswerMsg && activeAnswerMsg.resp ? (
          <WorkspacePane
            resp={activeAnswerMsg.resp}
            question={activeAnswerMsg.question}
            saving={saving}
            saveDisabled={saving || activeAnswerMsg.id !== latestAnswerMsg?.id}
            onSave={onSaveCurrent}
            isPinnedArchive={
              !!selectedAnswerId &&
              activeAnswerMsg.id !== latestAnswerMsg?.id
            }
            onUnpin={() => setSelectedAnswerId(null)}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/20 p-8 text-center text-sm text-muted-foreground">
            <Sparkles
              size={20}
              className="mb-3 text-muted-foreground/70"
              aria-hidden
            />
            <p className="max-w-sm">
              Пока нет готового ответа. Задай вопрос в чате слева — SQL,
              результат и интерпретация появятся здесь.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

function AssistantTurn({
  message,
  onAsk,
  isLatestAnswer,
  saving,
  onSave,
  compact = false,
  isActive = false,
  onSelect,
}: {
  message: Extract<ChatMessage, { role: "assistant" }>;
  onAsk: (q: string) => void;
  isLatestAnswer: boolean;
  saving: boolean;
  onSave: () => void;
  compact?: boolean;
  isActive?: boolean;
  onSelect?: () => void;
}) {
  if (message.pending) {
    return (
      <AnswerSkeleton
        fromCache={message.fromCache}
        stages={message.stages}
      />
    );
  }
  const resp = message.resp;
  if (!resp) return null;

  if (compact && resp.kind === "answer") {
    const summary = assistantSummary(resp);
    return (
      <button
        type="button"
        onClick={onSelect}
        title={isActive ? "Показывается в рабочей области" : "Открыть этот ответ в рабочей области"}
        className={cn(
          "group flex w-full items-start gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs leading-relaxed transition-colors",
          isActive
            ? "border-primary/50 bg-primary/5 text-foreground"
            : "border-transparent bg-transparent text-muted-foreground hover:border-border hover:bg-card/40 hover:text-foreground"
        )}
      >
        <div
          className={cn(
            "mt-1 h-1.5 w-1.5 shrink-0 rounded-full transition-colors",
            isActive
              ? "bg-primary"
              : isLatestAnswer
                ? "bg-primary/40 group-hover:bg-primary"
                : "bg-muted-foreground/40 group-hover:bg-muted-foreground"
          )}
          aria-hidden
        />
        <span className="flex-1">{summary || "Готово. Детали справа →"}</span>
      </button>
    );
  }

  const trace =
    message.stages && message.stages.length > 0 ? (
      <ThinkingTrace pending={false} stages={message.stages} />
    ) : null;

  if (resp.kind === "error" && resp.error) {
    return (
      <div className="space-y-3">
        {trace}
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Запрос заблокирован: {resp.error.code}</AlertTitle>
          <AlertDescription>
            {resp.error.hint_ru}
            {resp.sql && (
              <div className="mt-3">
                <SqlPreview sql={resp.sql} />
              </div>
            )}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (resp.kind === "clarify" && resp.clarify_question) {
    return (
      <div className="space-y-3">
        {trace}
        <Alert variant="warning">
          <CircleHelp className="h-4 w-4" />
          <AlertTitle>Нужно уточнение</AlertTitle>
          <AlertDescription>
            {resp.clarify_question}
            {resp.clarify_options && resp.clarify_options.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {resp.clarify_options.map((opt) => (
                  <button
                    key={opt.question}
                    type="button"
                    onClick={() => onAsk(opt.question)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/60 px-3 py-1 text-xs font-medium text-foreground transition-colors hover:border-foreground/40 hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
            {resp.sql && (
              <div className="mt-3">
                <SqlPreview sql={resp.sql} />
              </div>
            )}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (resp.kind === "answer" && resp.sql) {
    return (
      <div className="space-y-3">
        {trace}
        <AssistantCard
          resp={resp}
          saving={saving}
          saveDisabled={!isLatestAnswer || saving}
          onSave={onSave}
        />
      </div>
    );
  }

  return null;
}

function pluralizeRu(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

function EmptyHeader({ onPick }: { onPick: (q: string) => void }) {
  const { config } = useConfig();
  const { title, chips, kpis } = config.emptyState;

  return (
    <div className="flex h-full min-h-[55vh] flex-col items-center justify-center px-4 text-center">
      <h1 className="mb-3 text-3xl font-medium tracking-tight">{title}</h1>
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {chips.length > 0 && (
        <div className="mt-7 flex max-w-3xl flex-wrap items-center justify-center gap-2">
          {chips.map((c) => {
            const Icon = lucideByName(c.icon);
            return (
              <button
                key={`${c.label}-${c.prompt}`}
                type="button"
                onClick={() => onPick(c.prompt)}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-card/40 px-4 py-2 text-sm text-muted-foreground transition-colors hover:border-foreground/30 hover:bg-card hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Icon size={14} />
                {c.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function KpiStrip({ kpis }: { kpis: Array<{ value: string; label: string }> }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {kpis.map((k, i) => (
        <span key={`${k.value}-${k.label}`} className="flex items-center gap-x-3">
          <span>
            <strong className="text-foreground">{k.value}</strong> {k.label}
          </span>
          {i < kpis.length - 1 && <span aria-hidden="true">·</span>}
        </span>
      ))}
    </div>
  );
}

function ChatInputBar({
  busy,
  onSend,
  historyCount = 0,
}: {
  busy: boolean;
  onSend: (q: string) => void;
  historyCount?: number;
}) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const { config } = useConfig();

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  };

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  const canSubmit = !!text.trim() && !busy;
  const followUp = historyCount > 0;
  const placeholder = busy
    ? "Думаем…"
    : followUp
    ? "Спросите ещё…"
    : "Задайте вопрос";

  const turnsInContext = Math.min(historyCount, config.limits.historyLimit);

  return (
    <form
      onSubmit={submit}
      title={
        followUp
          ? `Контекст диалога: ${turnsInContext} ${
              turnsInContext === 1 ? "сообщение" : "сообщений"
            }. Модель учитывает предыдущие ответы.`
          : undefined
      }
      className="group mx-auto flex h-11 w-full items-center gap-1.5 rounded-full border border-border bg-card/60 pl-4 pr-1.5 transition-colors hover:bg-card focus-within:border-foreground/30"
    >
      <input
        ref={inputRef}
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        disabled={busy}
        className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
      />
      {followUp && (
        <span
          className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-muted-foreground"
          aria-label={`Контекст диалога: ${turnsInContext}`}
        >
          ctx·{turnsInContext}
        </span>
      )}
      <button
        type="submit"
        disabled={!canSubmit}
        aria-label="Отправить вопрос"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all hover:scale-[1.03] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
      >
        <ArrowUp size={14} strokeWidth={2.8} />
      </button>
    </form>
  );
}

function RoutePane({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  return <div className={cn(active ? "block" : "hidden")}>{children}</div>;
}

function UserQuestionBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[90%] rounded-2xl rounded-tr-md border border-border bg-card/80 px-4 py-2.5 text-sm text-foreground shadow-sm">
        {text}
      </div>
    </div>
  );
}
