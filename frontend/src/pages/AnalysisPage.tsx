import { useState } from "react";
import { BarChart3, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";
import { EvalDashboard } from "./EvalDashboard";
import { QueryLogPage } from "./QueryLogPage";

type Tab = "eval" | "log";

const TABS: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
  { id: "eval", label: "Оценка качества", icon: BarChart3 },
  { id: "log", label: "Журнал запросов", icon: ScrollText },
];

export function AnalysisPage() {
  const [tab, setTab] = useState<Tab>("eval");

  return (
    <div className="space-y-4">
      <div className="inline-flex h-9 items-center gap-0.5 rounded-lg bg-muted p-1">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon size={12} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className={cn(tab === "eval" ? "block" : "hidden")}>
        <EvalDashboard />
      </div>
      <div className={cn(tab === "log" ? "block" : "hidden")}>
        <QueryLogPage />
      </div>
    </div>
  );
}
