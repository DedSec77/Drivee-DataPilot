import { cn } from "@/lib/utils";
import {
  Activity,
  BookmarkCheck,
  BookOpen,
  Calendar,
  Database,
  type LucideIcon,
  MoreHorizontal,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ProfileBlock } from "@/components/ProfileBlock";
import { useConfig } from "@/config/ConfigContext";
import type { Conversation, Route, UserRole } from "@/types";

type Item = {
  id: Route;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: Item[] = [
  { id: "templates", label: "Шаблоны", icon: BookmarkCheck },
  { id: "schedules", label: "Расписания", icon: Calendar },
  { id: "dictionary", label: "Словарь", icon: BookOpen },
  { id: "datasource", label: "Источник данных", icon: Database },
  { id: "analysis", label: "Анализ", icon: Activity },
  { id: "settings", label: "Настройки", icon: Settings },
];

type Props = {
  current: Route;
  onNavigate: (r: Route) => void;
  open: boolean;
  onClose?: () => void;

  conversations: Conversation[];
  activeConversationId: string | null;
  onPickConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  busy: boolean;

  role: UserRole;
  onChangeRole: (r: UserRole) => void;
};

export function Sidebar({
  current,
  onNavigate,
  open,
  onClose,
  conversations,
  activeConversationId,
  onPickConversation,
  onNewChat,
  onDeleteConversation,
  busy,
  role,
  onChangeRole,
}: Props) {
  const { config } = useConfig();
  const closeOnMobile = () => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      onClose?.();
    }
  };

  const handleNavigate = (r: Route) => {
    onNavigate(r);
    closeOnMobile();
  };

  const handleNewChat = () => {
    onNewChat();
    onNavigate("ask");
    closeOnMobile();
  };

  const handlePickConversation = (id: string) => {
    onPickConversation(id);
    onNavigate("ask");
    closeOnMobile();
  };

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Закрыть меню"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden"
        />
      )}
      <aside
        className={cn(
          "flex h-full shrink-0 flex-col border-r border-border bg-card/40 transition-[width,transform] duration-200 ease-out",
          "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:bg-card",
          open
            ? "w-64 max-md:translate-x-0"
            : "max-md:w-64 max-md:-translate-x-full md:w-0 md:overflow-hidden md:border-r-0"
        )}
      >
                <div className="flex shrink-0 items-center gap-2.5 px-4 py-4">
          <img
            src={config.brand.markUrl}
            alt={config.brand.name}
            width={28}
            height={28}
            className="shrink-0 rounded-lg"
          />
          <span className="truncate text-sm font-semibold">
            {config.brand.name}
          </span>
        </div>

                <div className="px-3 pb-2">
          <button
            type="button"
            onClick={handleNewChat}
            disabled={busy}
            className={cn(
              "flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background/40 px-3 py-2 text-sm font-medium transition-colors",
              "hover:border-foreground/30 hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              "disabled:cursor-not-allowed disabled:opacity-60"
            )}
          >
            <Plus size={14} />
            Новый чат
          </button>
        </div>

                <div className="mt-2 flex min-h-0 flex-1 flex-col">
          <div className="px-4 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Недавние
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto scrollbar-thin px-2">
            {conversations.length === 0 ? (
              <div className="px-3 py-2 text-[11px] text-muted-foreground">
                Нет сохранённых чатов. Задайте первый вопрос — он появится
                здесь.
              </div>
            ) : (
              conversations.map((c) => {
                const active =
                  current === "ask" && c.id === activeConversationId;
                return (
                  <div
                    key={c.id}
                    className={cn(
                      "group relative flex items-center gap-1 rounded-md transition-colors",
                      active
                        ? "bg-accent text-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => handlePickConversation(c.id)}
                      className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
                      title={c.title}
                    >
                      {c.title || "Новый чат"}
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          aria-label="Действия с чатом"
                          className={cn(
                            "mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-opacity",
                            "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                            "hover:bg-background/60 hover:text-foreground"
                          )}
                        >
                          <MoreHorizontal size={14} />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="min-w-[180px]">
                        <DropdownMenuItem
                          onSelect={() => onDeleteConversation(c.id)}
                          className="text-destructive-foreground focus:bg-destructive/30 focus:text-destructive-foreground"
                        >
                          <Trash2 size={12} />
                          Удалить чат
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                );
              })
            )}
          </div>
        </div>

                <nav className="shrink-0 space-y-0.5 border-t border-border/60 px-2 py-2">
          {NAV_ITEMS.map((it) => {
            const active = current === it.id;
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                onClick={() => handleNavigate(it.id)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                )}
              >
                <Icon size={16} className="shrink-0" />
                <span className="truncate font-medium">{it.label}</span>
              </button>
            );
          })}
        </nav>

                <div className="shrink-0 border-t border-border/60 p-2">
          <ProfileBlock role={role} onChangeRole={onChangeRole} />
        </div>
      </aside>
    </>
  );
}
