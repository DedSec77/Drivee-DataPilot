import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { setApiBaseUrl } from "@/api";
import { DEFAULT_CONFIG } from "./defaults";
import {
  clearLocalOverrides,
  loadLocalOverrides,
  mergeConfig,
  resolveConfig,
  saveLocalOverrides,
} from "./storage";
import type { AppConfig, DeepPartial } from "./types";

type ConfigContextValue = {
  config: AppConfig;
  overrides: DeepPartial<AppConfig>;
  loading: boolean;
  updateOverrides: (patch: DeepPartial<AppConfig>) => void;
  replaceOverrides: (next: DeepPartial<AppConfig>) => void;
  resetOverrides: () => void;
};

const Ctx = createContext<ConfigContextValue | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [overrides, setOverrides] = useState<DeepPartial<AppConfig>>(
    () => loadLocalOverrides() ?? {}
  );
  const [fileCfg, setFileCfg] = useState<DeepPartial<AppConfig> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    resolveConfig().then(({ fileCfg }) => {
      if (cancelled) return;
      setFileCfg(fileCfg);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const config = useMemo(
    () => mergeConfig(DEFAULT_CONFIG, fileCfg, overrides),
    [fileCfg, overrides]
  );

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.style.fontSize = `${config.limits.uiScalePct}%`;
    document.documentElement.style.setProperty(
      "--brand-accent",
      config.brand.accentColor
    );
    document.documentElement.style.setProperty(
      "--brand-accent-foreground",
      config.brand.accentForeground
    );
  }, [
    config.brand.accentColor,
    config.brand.accentForeground,
    config.limits.uiScalePct,
  ]);

  useEffect(() => {
    setApiBaseUrl(config.api.baseUrl);
  }, [config.api.baseUrl]);

  const updateOverrides = useCallback((patch: DeepPartial<AppConfig>) => {
    setOverrides((prev) => {
      const next = mergePatchIntoOverrides(prev, patch);
      saveLocalOverrides(next);
      return next;
    });
  }, []);

  const replaceOverrides = useCallback((next: DeepPartial<AppConfig>) => {
    saveLocalOverrides(next);
    setOverrides(next);
  }, []);

  const resetOverrides = useCallback(() => {
    clearLocalOverrides();
    setOverrides({});
  }, []);

  const value = useMemo<ConfigContextValue>(
    () => ({
      config,
      overrides,
      loading,
      updateOverrides,
      replaceOverrides,
      resetOverrides,
    }),
    [config, overrides, loading, updateOverrides, replaceOverrides, resetOverrides]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useConfig(): ConfigContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useConfig must be used inside <ConfigProvider>");
  return v;
}

function mergePatchIntoOverrides(
  prev: DeepPartial<AppConfig>,
  patch: DeepPartial<AppConfig>
): DeepPartial<AppConfig> {
  const out: any = { ...prev };
  for (const key of Object.keys(patch) as Array<keyof AppConfig>) {
    const pv = (patch as any)[key];
    if (pv === undefined) continue;
    if (Array.isArray(pv)) {
      out[key] = pv;
    } else if (pv && typeof pv === "object") {
      out[key] = { ...(prev as any)[key], ...pv };
    } else {
      out[key] = pv;
    }
  }
  return out;
}
