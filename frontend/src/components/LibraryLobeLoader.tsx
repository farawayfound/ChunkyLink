import { useId } from "react";

/** Queued + Completed stay animated until the job advances or the artifact is acted on. */
const STATUS_TO_VARIANT: Record<string, "c1" | "c2" | "c3" | "c4"> = {
  queued: "c2",
  crawling: "c1",
  synthesizing: "c4",
  review: "c3",
};

export function libraryStatusUsesLobeLoader(status: string): boolean {
  return status in STATUS_TO_VARIANT;
}

export function LibraryLobeLoader({ status }: { status: string }) {
  const rawId = useId();
  const filterId = `lib-goo-soft-${rawId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const href = `url(#${filterId})`;
  const v = STATUS_TO_VARIANT[status];
  if (!v) return null;

  return (
    <svg className="library-lobe-svg" viewBox="0 0 50 50" aria-hidden>
      <defs>
        <filter id={filterId} x="-35%" y="-35%" width="170%" height="170%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
          <feColorMatrix
            in="blur"
            mode="matrix"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 14 -6"
            result="goo"
          />
        </filter>
      </defs>
        {v === "c1" && (
          <g filter={href} fill="currentColor">
            <ellipse className="lib-lobe-c1-l1" cx="0" cy="0" rx="7" ry="5.5" />
            <ellipse className="lib-lobe-c1-l2" cx="0" cy="0" rx="7" ry="5.5" />
            <ellipse className="lib-lobe-c1-l3" cx="0" cy="0" rx="7" ry="5.5" />
          </g>
        )}
        {v === "c2" && (
          <g filter={href}>
            <circle className="lib-lobe-c2-core" cx="0" cy="0" r="5" fill="currentColor" />
            <ellipse className="lib-lobe-c2-l1" cx="0" cy="0" rx="6" ry="4.5" fill="currentColor" />
            <ellipse
              className="lib-lobe-c2-l2"
              cx="0"
              cy="0"
              rx="5"
              ry="3.5"
              fill="currentColor"
              opacity={0.78}
            />
          </g>
        )}
        {v === "c3" && (
          <g filter={href}>
            <ellipse className="lib-lobe-c3-l1" cx="0" cy="0" rx="8" ry="6" fill="currentColor" />
            <ellipse
              className="lib-lobe-c3-l2"
              cx="0"
              cy="0"
              rx="7"
              ry="5.5"
              fill="currentColor"
              opacity={0.78}
            />
            <ellipse className="lib-lobe-c3-l3" cx="0" cy="0" rx="7" ry="5.5" fill="currentColor" />
          </g>
        )}
        {v === "c4" && (
          <g filter={href}>
            <circle className="lib-lobe-c4-core" cx="25" cy="25" r="5" fill="currentColor" />
            <ellipse className="lib-lobe-c4-l1" cx="0" cy="0" rx="5" ry="4" fill="currentColor" />
            <ellipse className="lib-lobe-c4-l2" cx="0" cy="0" rx="5" ry="4" fill="currentColor" />
            <ellipse className="lib-lobe-c4-l3" cx="0" cy="0" rx="5" ry="4" fill="currentColor" />
          </g>
        )}
    </svg>
  );
}
