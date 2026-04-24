import { Check, ChevronsUpDown, ShieldCheck, User } from "lucide-react";
import * as LucideIcons from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useConfig } from "@/config/ConfigContext";
import type { LucideIcon } from "lucide-react";
import type { UserRole } from "@/types";

type Props = {
  role: UserRole;
  onChangeRole: (r: UserRole) => void;
};

function lucideOr(name: string | undefined, fallback: LucideIcon): LucideIcon {
  if (!name) return fallback;
  const Icon = (LucideIcons as unknown as Record<string, LucideIcon | undefined>)[name];
  return Icon ?? fallback;
}

export function ProfileBlock({ role, onChangeRole }: Props) {
  const { config } = useConfig();
  const roles = config.roles;
  const accent = config.brand.accentColor;
  const accentFg = config.brand.accentForeground;

  const current =
    roles.find((r) => r.id === role) ??
    roles.find((r) => r.isDefault) ??
    roles[0];

  if (!current) {
    return (
      <div className="px-2 py-2 text-xs text-muted-foreground">
        Роли не настроены. Откройте «Настройки» → «Роли».
      </div>
    );
  }

  const initial = (Array.from(current.label.trim())[0] ?? "?").toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "group flex w-full items-center gap-2.5 rounded-md border border-transparent px-2 py-2 text-left transition-colors",
            "hover:border-border hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          )}
        >
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
            style={{ backgroundColor: accent, color: accentFg }}
            aria-hidden
          >
            {initial}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-medium text-foreground">
              {current.label}
            </span>
            {config.brand.byline && (
              <span className="truncate text-[10px] text-muted-foreground">
                {config.brand.byline}
              </span>
            )}
          </div>
          <ChevronsUpDown
            size={14}
            className="shrink-0 text-muted-foreground transition-colors group-hover:text-foreground"
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60">
        <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Роль доступа
        </DropdownMenuLabel>
        {roles.map((r) => {
          const Icon = lucideOr(r.icon, r.id === "analyst" ? ShieldCheck : User);
          const active = r.id === role;
          return (
            <DropdownMenuItem
              key={r.id}
              onSelect={() => onChangeRole(r.id)}
              className="flex items-start gap-2"
            >
              <Icon size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium leading-none">{r.label}</div>
                {r.hint && (
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {r.hint}
                  </div>
                )}
              </div>
              {active && (
                <Check size={14} className="mt-0.5 shrink-0 text-foreground" />
              )}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[10px] text-muted-foreground font-normal">
          Роль определяет доступ к PII и применяется ко всем запросам.
        </DropdownMenuLabel>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
