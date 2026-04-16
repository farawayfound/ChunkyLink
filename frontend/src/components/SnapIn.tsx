import { useEffect, useRef } from "react";

type Edge = "left" | "right" | "top" | "bottom";

interface Props {
  children: React.ReactNode;
  from?: Edge;
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
  /** If true, skip animation (e.g. reduced-motion or already visible) */
  skip?: boolean;
}

/**
 * Wraps a section and snaps it in from the given viewport edge on mount.
 * Uses a CSS class toggle so it's GPU-composited and zero-JS-per-frame.
 */
export function SnapIn({ children, from = "bottom", delay = 0, className = "", style, skip = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || skip) {
      el?.classList.add("snap-in--visible");
      return;
    }

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) {
      el.classList.add("snap-in--visible");
      return;
    }

    const timer = setTimeout(() => {
      el.classList.add("snap-in--visible");
    }, delay);

    return () => clearTimeout(timer);
  }, [delay, skip]);

  return (
    <div
      ref={ref}
      className={`snap-in snap-in--from-${from}${className ? ` ${className}` : ""}`}
      style={style}
    >
      {children}
    </div>
  );
}
