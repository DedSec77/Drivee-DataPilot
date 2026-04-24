import { ThinkingTrace } from "@/components/ThinkingTrace";
import type { StageEvent } from "@/types";

export function AnswerSkeleton({
  fromCache,
  stages,
}: {
  fromCache?: boolean;
  stages?: StageEvent[];
}) {
  return <ThinkingTrace pending stages={stages} fromCache={fromCache} />;
}
