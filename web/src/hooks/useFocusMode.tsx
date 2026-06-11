import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface FocusModeContextValue {
  enabled: boolean;
  toggle: () => void;
}

const STORAGE_KEY = "storyforge3.focusMode";
const FocusModeContext = createContext<FocusModeContextValue | null>(null);

export function FocusModeProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(() => localStorage.getItem(STORAGE_KEY) === "true");

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(enabled));
    document.documentElement.dataset.focusMode = enabled ? "true" : "false";
  }, [enabled]);

  const value = useMemo(
    () => ({
      enabled,
      toggle: () => setEnabled((current) => !current)
    }),
    [enabled]
  );

  return <FocusModeContext.Provider value={value}>{children}</FocusModeContext.Provider>;
}

export function useFocusMode() {
  const value = useContext(FocusModeContext);
  if (!value) {
    throw new Error("useFocusMode must be used inside FocusModeProvider");
  }
  return value;
}
