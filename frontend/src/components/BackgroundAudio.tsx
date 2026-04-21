import { useEffect, useRef, useState } from "react";
import { useUISettings } from "./UISettingsContext";

const TRACK_PATH =
  "/uploads/media/" + encodeURIComponent("A-SIDE - STAY - INSTRUMENTAL.wav");

/** Site-wide loop; starts muted for autoplay policy, unmutes after first user gesture unless user has muted. */
export function BackgroundAudio() {
  const ref = useRef<HTMLAudioElement>(null);
  const { musicMuted } = useUISettings();
  const [gestureReceived, setGestureReceived] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const el = ref.current;
    if (!el) return;

    el.volume = 0.35;
    void el.play().catch(() => {});

    const onGesture = () => {
      setGestureReceived(true);
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);

    return () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const shouldMute = musicMuted || !gestureReceived;
    el.muted = shouldMute;
    if (!shouldMute) void el.play().catch(() => {});
  }, [musicMuted, gestureReceived]);

  if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return null;
  }

  return (
    <audio
      ref={ref}
      src={TRACK_PATH}
      loop
      preload="metadata"
      aria-hidden="true"
      style={{
        position: "fixed",
        width: 0,
        height: 0,
        opacity: 0,
        pointerEvents: "none",
      }}
    />
  );
}
