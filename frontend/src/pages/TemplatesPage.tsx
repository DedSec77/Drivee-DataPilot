import { TemplatesPanel } from "@/components/TemplatesPanel";
import type { Template } from "@/types";

type Props = {
  templates: Template[];
  onPick: (t: Template) => void;
  onApprove: (t: Template) => void;
  onDelete: (t: Template) => void;
};

export function TemplatesPage({ templates, onPick, onApprove, onDelete }: Props) {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <header className="mb-4">
        <h1 className="text-xl font-medium tracking-tight">Шаблоны</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Сохранённые вопросы. Одобренные шаблоны попадают в few-shot индекс
          и улучшают ответы похожих запросов.
        </p>
      </header>
      <TemplatesPanel
        templates={templates}
        onPick={onPick}
        onApprove={onApprove}
        onDelete={onDelete}
      />
    </div>
  );
}
