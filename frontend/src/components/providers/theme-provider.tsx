import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { getActiveEdition, type AppEdition } from "@/config/edition";

export type Theme = "light" | "dark" | "system";

export type ColorThemeId =
  | "solo-terracotta"
  | "vesper-indigo"
  | "sovereign-emerald"
  | "cobalt-sapphire"
  | "amethyst-quartz"
  | "cyber-lagoon";

export interface ColorThemeOption {
  id: ColorThemeId;
  name: string;
  subtitle: string;
  primaryHex: string;
  surfaceDarkHex: string;
  surfaceLightHex: string;
  badge?: string;
}

export const M3_COLOR_THEMES: ColorThemeOption[] = [
  {
    id: "sovereign-emerald",
    name: "Vesper Emerald",
    subtitle: "Signature Vesper green — jade on deep forest obsidian",
    primaryHex: "#10B981",
    surfaceDarkHex: "#051510",
    surfaceLightHex: "#F0FAF5",
    badge: "Vesper",
  },
  {
    id: "solo-terracotta",
    name: "Warm Ember (Terracotta)",
    subtitle: "Refined terracotta copper on warm espresso stone",
    primaryHex: "#E05A2B",
    surfaceDarkHex: "#12100E",
    surfaceLightHex: "#FAF7F2",
    badge: "Solo",
  },
  {
    id: "vesper-indigo",
    name: "Nocturne (Indigo)",
    subtitle: "Iris indigo on deep starlight slate",
    primaryHex: "#6366F1",
    surfaceDarkHex: "#0B0D14",
    surfaceLightHex: "#F8FAFC",
  },
  {
    id: "cobalt-sapphire",
    name: "Cobalt Sapphire (Ocean)",
    subtitle: "Royal cobalt on titanium navy",
    primaryHex: "#3B82F6",
    surfaceDarkHex: "#090E17",
    surfaceLightHex: "#F6F9FE",
  },
  {
    id: "amethyst-quartz",
    name: "Amethyst Quartz (Violet)",
    subtitle: "Electric violet on deep amethyst",
    primaryHex: "#8B5CF6",
    surfaceDarkHex: "#0E0B16",
    surfaceLightHex: "#FAF8FF",
  },
  {
    id: "cyber-lagoon",
    name: "Cyber Lagoon (Cyan)",
    subtitle: "Luminous cyan on abyssal teal-slate",
    primaryHex: "#06B6D4",
    surfaceDarkHex: "#071014",
    surfaceLightHex: "#F4FBFE",
  },
];

const COLOR_THEME_KEY = "contextuai-color-theme";
/** Set only when the user explicitly picks a theme; otherwise the theme follows the edition. */
const COLOR_THEME_EXPLICIT_KEY = "contextuai-color-theme-explicit";

const VALID_IDS = new Set<ColorThemeId>(M3_COLOR_THEMES.map((t) => t.id));

/** Brand default per edition: Vesper → Emerald, Solo → Terracotta. */
export function defaultColorThemeFor(edition: AppEdition): ColorThemeId {
  return edition === "lite" ? "sovereign-emerald" : "solo-terracotta";
}

function readInitialColorTheme(): ColorThemeId {
  if (typeof window === "undefined") return "sovereign-emerald";
  try {
    const explicit = localStorage.getItem(COLOR_THEME_EXPLICIT_KEY) === "1";
    const stored = localStorage.getItem(COLOR_THEME_KEY) as ColorThemeId | null;
    if (explicit && stored && VALID_IDS.has(stored)) return stored;
  } catch {
    // ignore storage errors
  }
  return defaultColorThemeFor(getActiveEdition());
}

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
  colorTheme: ColorThemeId;
  setColorTheme: (colorTheme: ColorThemeId) => void;
  /** Clear the explicit choice and follow the edition's brand theme again. */
  resetColorThemeToBrand: () => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "system",
  setTheme: () => {},
  resolvedTheme: "dark",
  colorTheme: "sovereign-emerald",
  setColorTheme: () => {},
  resetColorThemeToBrand: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("theme") as Theme) || "system";
    }
    return "system";
  });

  const [colorTheme, setColorThemeState] = useState<ColorThemeId>(readInitialColorTheme);

  const getResolvedTheme = (t: Theme): "light" | "dark" => {
    if (t === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return t;
  };

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() => getResolvedTheme(theme));

  const setColorTheme = useCallback((next: ColorThemeId) => {
    try {
      localStorage.setItem(COLOR_THEME_EXPLICIT_KEY, "1");
    } catch {
      // ignore
    }
    setColorThemeState(next);
  }, []);

  const resetColorThemeToBrand = useCallback(() => {
    try {
      localStorage.removeItem(COLOR_THEME_EXPLICIT_KEY);
    } catch {
      // ignore
    }
    setColorThemeState(defaultColorThemeFor(getActiveEdition()));
  }, []);

  useEffect(() => {
    const resolved = getResolvedTheme(theme);
    setResolvedTheme(resolved);
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(resolved);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.colorTheme = colorTheme;
    localStorage.setItem(COLOR_THEME_KEY, colorTheme);
  }, [colorTheme]);

  // Follow the edition's brand theme (Vesper ↔ Solo) unless the user picked one.
  useEffect(() => {
    const handler = (e: Event) => {
      let explicit = false;
      try {
        explicit = localStorage.getItem(COLOR_THEME_EXPLICIT_KEY) === "1";
      } catch {
        // ignore
      }
      if (explicit) return;
      const detail = (e as CustomEvent<AppEdition>).detail;
      const edition: AppEdition = detail === "lite" || detail === "solo" ? detail : getActiveEdition();
      setColorThemeState(defaultColorThemeFor(edition));
    };
    window.addEventListener("contextuai:edition-changed", handler);
    return () => window.removeEventListener("contextuai:edition-changed", handler);
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const resolved = getResolvedTheme("system");
      setResolvedTheme(resolved);
      document.documentElement.classList.remove("light", "dark");
      document.documentElement.classList.add(resolved);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider
      value={{ theme, setTheme, resolvedTheme, colorTheme, setColorTheme, resetColorThemeToBrand }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
