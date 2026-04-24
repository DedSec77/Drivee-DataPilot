import { BookmarkCheck, BookmarkPlus, Check, MoreHorizontal, Trash2 } from "lucide-react";
import type { Template } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type Props = {
  templates: Template[];
  onPick: (t: Template) => void;
  onSaveCurrent?: () => void;
  onApprove?: (t: Template) => void;
  onDelete?: (t: Template) => void;
  saveDisabled?: boolean;
};

export function TemplatesPanel({
  templates,
  onPick,
  onSaveCurrent,
  onApprove,
  onDelete,
  saveDisabled,
}: Props) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <BookmarkCheck size={14} className="text-muted-foreground" />
          Шаблоны
        </CardTitle>
        {onSaveCurrent && (
          <Button
            size="sm"
            onClick={onSaveCurrent}
            disabled={saveDisabled}
            className="gap-1"
          >
            <BookmarkPlus size={12} /> Сохранить
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex max-h-[26rem] flex-col gap-1 overflow-y-auto scrollbar-thin px-3 py-3">
          {templates.length === 0 ? (
            <div className="px-1 py-3 text-xs text-muted-foreground">
              Нет шаблонов. Сохраните ответ на свой вопрос — после одобрения
              шаблон попадёт в индекс few-shot и будет использоваться в похожих
              запросах.
            </div>
          ) : (
            templates.map((t) => (
              <div
                key={t.report_id}
                className="group flex items-start justify-between gap-1 rounded-md border border-transparent px-2 py-2 text-sm transition-colors hover:border-border hover:bg-accent/30"
              >
                <button
                  onClick={() => onPick(t)}
                  className="flex-1 text-left"
                >
                  <div className="font-medium line-clamp-1">{t.title}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                    {t.nl_question}
                  </div>
                  {t.is_approved && (
                    <Badge variant="success" className="mt-1.5">
                      <Check size={10} /> одобрен
                    </Badge>
                  )}
                </button>

                {(onApprove || onDelete) && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Действия с шаблоном"
                        className="h-7 w-7 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
                      >
                        <MoreHorizontal size={14} />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="min-w-[200px]">
                      {onApprove && !t.is_approved && (
                        <DropdownMenuItem onSelect={() => onApprove(t)}>
                          <Check size={12} />
                          Одобрить и добавить в индекс
                        </DropdownMenuItem>
                      )}
                      {onApprove && !t.is_approved && onDelete && (
                        <DropdownMenuSeparator />
                      )}
                      {onDelete && (
                        <DropdownMenuItem
                          onSelect={() => onDelete(t)}
                          className="text-destructive-foreground focus:bg-destructive/30 focus:text-destructive-foreground"
                        >
                          <Trash2 size={12} />
                          Удалить шаблон
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
