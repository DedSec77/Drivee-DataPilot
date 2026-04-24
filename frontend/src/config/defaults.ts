import type { AppConfig } from "./types";

export const DEFAULT_CONFIG: AppConfig = {
  brand: {
    name: "DataPilot",
    byline: "Drivee · MVP",
    markUrl: "/drivee-mark.svg",
    wordmarkUrl: "/drivee-wordmark.svg",
    accentColor: "#96EA28",
    accentForeground: "#0A0A0A",
  },

  emptyState: {
    title: "С чего начнём?",
    chips: [
      {
        icon: "PieChart",
        label: "Топ-3 по отменам",
        prompt: "Топ-3 города по количеству отменённых заказов на этой неделе",
      },
      {
        icon: "BarChart3",
        label: "Отмены по городам",
        prompt: "Сколько отмен по городам за прошлую неделю?",
      },
      {
        icon: "TrendingUp",
        label: "Конверсия по каналам",
        prompt: "Сравни конверсию по каналам за последние 30 дней.",
      },
      {
        icon: "Wallet",
        label: "Средний чек",
        prompt: "Средний чек по сегментам пользователей за прошлый месяц.",
      },
    ],
    kpis: [],
  },

  roles: [
    {
      id: "business_user",
      label: "Менеджер",
      hint: "только агрегаты, без PII",
      icon: "User",
      isDefault: true,
    },
    {
      id: "analyst",
      label: "Аналитик",
      hint: "+ маски PII, одобрение шаблонов",
      icon: "ShieldCheck",
    },
  ],

  cronPresets: [
    { label: "Каждую минуту (тест)", expr: "* * * * *" },
    { label: "Каждый понедельник 9:00", expr: "0 9 * * 1" },
    { label: "Каждый день в 8:00", expr: "0 8 * * *" },
    { label: "Первое число месяца", expr: "0 9 1 * *" },
  ],

  limits: {
    historyLimit: 6,
    templateOwner: "analyst",
    uiScalePct: 140,
  },

  api: {
    baseUrl:
      ((import.meta as any).env?.VITE_API_URL as string | undefined) ??
      "http://localhost:8000",
  },
};
