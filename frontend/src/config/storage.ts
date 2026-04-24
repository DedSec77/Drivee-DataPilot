import { DEFAULT_CONFIG } from "./defaults";
import type { AppConfig, DeepPartial } from "./types";

const LOCAL_KEY = "drivee.config.overrides";

export function mergeConfig(
  base: AppConfig,
  ...patches: Array<DeepPartial<AppConfig> | undefined | null>
): AppConfig {
  let out: any = { ...base };
  for (const p of patches) {
    if (!p) continue;
    out = mergeDeep(out, p);
  }
  return out as AppConfig;
}

function mergeDeep(target: any, source: any): any {
  if (Array.isArray(source)) return source;
  if (source === null || typeof source !== "object") return source;
  const out: any = Array.isArray(target) ? [...target] : { ...target };
  for (const key of Object.keys(source)) {
    const sv = source[key];
    if (sv === undefined) continue;
    if (sv && typeof sv === "object" && !Array.isArray(sv)) {
      out[key] = mergeDeep(target?.[key] ?? {}, sv);
    } else {
      out[key] = sv;
    }
  }
  return out;
}

export async function fetchFileConfig(): Promise<DeepPartial<AppConfig> | null> {
  try {
    const res = await fetch("/config.json", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as DeepPartial<AppConfig>;
  } catch {
    return null;
  }
}

export function loadLocalOverrides(): DeepPartial<AppConfig> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DeepPartial<AppConfig>;
  } catch {
    return null;
  }
}

export function saveLocalOverrides(overrides: DeepPartial<AppConfig>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCAL_KEY, JSON.stringify(overrides));
}

export function clearLocalOverrides(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LOCAL_KEY);
}

export async function resolveConfig(): Promise<{
  effective: AppConfig;
  fileCfg: DeepPartial<AppConfig> | null;
  localCfg: DeepPartial<AppConfig> | null;
}> {
  const fileCfg = await fetchFileConfig();
  const localCfg = loadLocalOverrides();
  return {
    effective: mergeConfig(DEFAULT_CONFIG, fileCfg, localCfg),
    fileCfg,
    localCfg,
  };
}
