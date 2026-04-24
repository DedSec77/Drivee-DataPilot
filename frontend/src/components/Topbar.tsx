import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConfig } from "@/config/ConfigContext";
import type { Route } from "@/types";

const TITLES: Record<Route, string> = {
  ask: "Чат",
  templates: "Шаблоны",
  schedules: "Расписания",
  dictionary: "Словарь",
  datasource: "Источник данных",
  analysis: "Анализ",
  settings: "Настройки",
};

type Props = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  route: Route;
};

export function Topbar({ sidebarOpen, onToggleSidebar, route }: Props) {
  const { config } = useConfig();
  return (
    <div className="sticky top-0 z-20 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-sm">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-foreground"
        onClick={onToggleSidebar}
        aria-label={sidebarOpen ? "Свернуть меню" : "Показать меню"}
      >
        <PanelLeft size={16} />
      </Button>
      <div className="h-4 w-px bg-border" />
      <span className="truncate text-sm font-medium">{TITLES[route]}</span>

      <div className="ml-auto hidden items-center gap-2 text-[11px] text-muted-foreground md:flex">
        <img
          src={config.brand.wordmarkUrl}
          alt={config.brand.name}
          height={18}
          className="h-4"
        />
      </div>
    </div>
  );
}
