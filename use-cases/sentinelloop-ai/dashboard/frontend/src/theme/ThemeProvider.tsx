import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { applyTheme, readTheme, setTheme as persistTheme, subscribeTheme, type ThemeName } from "./theme";

type ThemeContextValue = {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
  toggle: () => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  setTheme: persistTheme,
  toggle: () => persistTheme(readTheme() === "dark" ? "light" : "dark"),
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(() => (typeof document === "undefined" ? "dark" : readTheme()));

  useEffect(() => {
    applyTheme(theme);
    return subscribeTheme(() => setThemeState(readTheme()));
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: (next) => {
        persistTheme(next);
        setThemeState(next);
      },
      toggle: () => {
        const next = theme === "dark" ? "light" : "dark";
        persistTheme(next);
        setThemeState(next);
      },
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
