import { createContext, useCallback, useContext, useEffect, useState } from "react";

interface UISettingsCtx {
  musicMuted: boolean;
  toggleMusicMuted: () => void;
  staticBackground: boolean;
  toggleStaticBackground: () => void;
}

const STORAGE_MUTE = "cl:musicMuted";
const STORAGE_BG = "cl:staticBackground";

function readBool(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeBool(key: string, value: boolean) {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    /* ignore */
  }
}

const Ctx = createContext<UISettingsCtx>({
  musicMuted: false,
  toggleMusicMuted: () => {},
  staticBackground: false,
  toggleStaticBackground: () => {},
});

export function UISettingsProvider({ children }: { children: React.ReactNode }) {
  const [musicMuted, setMusicMuted] = useState<boolean>(() => readBool(STORAGE_MUTE));
  const [staticBackground, setStaticBackground] = useState<boolean>(() => readBool(STORAGE_BG));

  useEffect(() => writeBool(STORAGE_MUTE, musicMuted), [musicMuted]);
  useEffect(() => writeBool(STORAGE_BG, staticBackground), [staticBackground]);

  const toggleMusicMuted = useCallback(() => setMusicMuted((m) => !m), []);
  const toggleStaticBackground = useCallback(() => setStaticBackground((s) => !s), []);

  return (
    <Ctx.Provider value={{ musicMuted, toggleMusicMuted, staticBackground, toggleStaticBackground }}>
      {children}
    </Ctx.Provider>
  );
}

export function useUISettings() {
  return useContext(Ctx);
}
