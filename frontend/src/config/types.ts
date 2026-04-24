import type { UserRole } from "@/types";

export type BrandConfig = {
  name: string;
  byline: string;
  markUrl: string;
  wordmarkUrl: string;
  accentColor: string;
  accentForeground: string;
};

export type EmptyChip = {
  icon: string;
  label: string;
  prompt: string;
};

export type EmptyKpi = {
  value: string;
  label: string;
};

export type EmptyStateConfig = {
  title: string;
  chips: EmptyChip[];
  kpis: EmptyKpi[];
};

export type RoleOption = {
  id: UserRole;
  label: string;
  hint: string;
  icon?: string;
  isDefault?: boolean;
};

export type CronPreset = {
  label: string;
  expr: string;
};

export type LimitsConfig = {
  historyLimit: number;
  templateOwner: string;
  uiScalePct: number;
};

export type ApiConfig = {
  baseUrl: string;
};

export type AppConfig = {
  brand: BrandConfig;
  emptyState: EmptyStateConfig;
  roles: RoleOption[];
  cronPresets: CronPreset[];
  limits: LimitsConfig;
  api: ApiConfig;
};

export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends Array<infer U>
    ? Array<U>
    : T[P] extends object
      ? DeepPartial<T[P]>
      : T[P];
};
