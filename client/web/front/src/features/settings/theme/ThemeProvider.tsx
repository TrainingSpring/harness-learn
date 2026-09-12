import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "system" | "light" | "dark";

interface ThemeContextValue {
  /** 用户选择的偏好；system 不等于当前最终生效的明暗值。 */
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const STORAGE_KEY = "harness-theme";
const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredTheme(): Theme {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

/** 管理浏览器主题偏好，并在 system 模式下跟随操作系统实时变化。 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.themePreference = theme;
    };
    apply();
    media.addEventListener("change", apply);
    localStorage.setItem(STORAGE_KEY, theme);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** 读取和修改主题，只能在 ThemeProvider 内使用。 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme 必须在 ThemeProvider 内使用");
  return context;
}
