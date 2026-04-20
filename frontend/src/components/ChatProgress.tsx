import { useId } from "react";
import type { ChatPhase } from "../hooks/useChat";

/** Organic loaders: B = metaballs (default), A = path morph blobs (e.g. Workspace chat). */
export type ChatProgressLoaderVariant = "metaball" | "pathMorph";

interface Props {
  phase: ChatPhase;
  /** Live model reasoning text while in thinking / early answering. */
  thinking?: string;
  /** After first answer token: collapse thinking strip to one line in the status area. */
  minimizeThinking?: boolean;
  /** Animated icon style for the active step. */
  loaderVariant?: ChatProgressLoaderVariant;
}

const STAGES: { key: ChatPhase; label: string }[] = [
  { key: "sending", label: "Processing prompt" },
  { key: "searching", label: "Searching index" },
  { key: "thinking", label: "Thinking" },
  { key: "answering", label: "Generating response" },
];

function phaseIndex(phase: ChatPhase): number {
  return STAGES.findIndex((s) => s.key === phase);
}

/** Variant B metaballs from Organic Loaders — one SVG per active stage (0–3). */
function ChatProgressMetaball({ stage, filterId }: { stage: number; filterId: string }) {
  const href = `url(#${filterId})`;
  const fill = "currentColor";
  switch (stage) {
    case 0:
      return (
        <svg className="chat-progress-mb-svg" viewBox="0 0 50 50" aria-hidden>
          <g filter={href} fill={fill}>
            <circle className="chat-mb-b1-core" cx="20" cy="25" r="7" />
            <circle className="chat-mb-b1-feed chat-mb-b1-f1" cx="0" cy="0" r="4" />
            <circle className="chat-mb-b1-feed chat-mb-b1-f2" cx="0" cy="0" r="3.5" />
            <circle className="chat-mb-b1-feed chat-mb-b1-f3" cx="0" cy="0" r="3" />
          </g>
        </svg>
      );
    case 1:
      return (
        <svg className="chat-progress-mb-svg" viewBox="0 0 50 50" aria-hidden>
          <g filter={href} fill={fill}>
            <circle className="chat-mb-b2-core" cx="25" cy="25" r="7" />
            <circle className="chat-mb-b2-sat1" cx="0" cy="0" r="3.5" />
            <circle className="chat-mb-b2-sat2" cx="0" cy="0" r="2.8" />
          </g>
        </svg>
      );
    case 2:
      return (
        <svg className="chat-progress-mb-svg" viewBox="0 0 50 50" aria-hidden>
          <g filter={href} fill={fill}>
            <circle className="chat-mb-b3-a" cx="0" cy="0" r="7" />
            <circle className="chat-mb-b3-b" cx="0" cy="0" r="6.5" />
            <circle className="chat-mb-b3-c" cx="0" cy="0" r="5" />
          </g>
        </svg>
      );
    case 3:
      return (
        <svg className="chat-progress-mb-svg" viewBox="0 0 50 50" aria-hidden>
          <g filter={href} fill={fill}>
            <circle className="chat-mb-b4-src" cx="18" cy="25" r="8" />
            <circle className="chat-mb-b4-drop chat-mb-b4-e1" cx="0" cy="0" r="3" />
            <circle className="chat-mb-b4-drop chat-mb-b4-e2" cx="0" cy="0" r="2.4" />
            <circle className="chat-mb-b4-drop chat-mb-b4-e3" cx="0" cy="0" r="2" />
          </g>
        </svg>
      );
    default:
      return null;
  }
}

/** Variant A — path morph blobs (Organic loaders section A). */
function ChatProgressPathMorph({ stage }: { stage: number }) {
  const fill = "currentColor";
  switch (stage) {
    case 0:
      return (
        <svg className="chat-progress-path-svg" viewBox="0 0 50 50" aria-hidden>
          <path
            className="chat-path-a1-body"
            fill={fill}
            d="M10 25 C 10 16, 18 9, 30 9 C 40 9, 44 17, 44 25 C 44 33, 40 41, 30 41 C 18 41, 10 34, 10 25 Z"
          />
          <ellipse
            className="chat-path-a1-streak chat-path-a1-s1"
            cx="40"
            cy="22"
            rx="4"
            ry="1.6"
            fill={fill}
          />
          <ellipse
            className="chat-path-a1-streak chat-path-a1-s2"
            cx="42"
            cy="25"
            rx="4"
            ry="1.6"
            fill={fill}
          />
          <ellipse
            className="chat-path-a1-streak chat-path-a1-s3"
            cx="40"
            cy="28"
            rx="4"
            ry="1.6"
            fill={fill}
          />
        </svg>
      );
    case 1:
      return (
        <svg className="chat-progress-path-svg" viewBox="0 0 50 50" aria-hidden>
          <path
            className="chat-path-a2-body"
            fill={fill}
            d="M25 6 C 36 6, 44 12, 44 25 C 44 38, 36 44, 25 44 C 14 44, 6 38, 6 25 C 6 12, 14 6, 25 6 Z"
          />
        </svg>
      );
    case 2:
      return (
        <svg className="chat-progress-path-svg" viewBox="0 0 50 50" aria-hidden>
          <path
            className="chat-path-a3-body"
            fill={fill}
            d="M25 8 C 38 10, 42 18, 41 27 C 40 37, 31 42, 22 41 C 12 40, 8 31, 10 22 C 12 13, 18 7, 25 8 Z"
          />
          <ellipse
            className="chat-path-a3-core"
            cx="25"
            cy="25"
            rx="6"
            ry="4"
            fill={fill}
            opacity={0.65}
          />
        </svg>
      );
    case 3:
      return (
        <svg className="chat-progress-path-svg" viewBox="0 0 50 50" aria-hidden>
          <path
            className="chat-path-a4-body"
            fill={fill}
            d="M20 25 C 20 14, 30 8, 36 10 C 42 12, 42 20, 40 25 C 42 30, 42 38, 36 40 C 30 42, 20 36, 20 25 Z"
          />
          <circle className="chat-path-a4-drop chat-path-a4-d1" cx="40" cy="25" r="2" fill={fill} />
          <circle className="chat-path-a4-drop chat-path-a4-d2" cx="40" cy="22" r="1.4" fill={fill} />
          <circle className="chat-path-a4-drop chat-path-a4-d3" cx="40" cy="28" r="1.6" fill={fill} />
        </svg>
      );
    default:
      return null;
  }
}

export function ChatProgress({
  phase,
  thinking = "",
  minimizeThinking = false,
  loaderVariant = "metaball",
}: Props) {
  const rawId = useId();
  const gooFilterId = `chat-mb-goo-${rawId.replace(/[^a-zA-Z0-9_-]/g, "")}`;

  if (phase === "idle") return null;

  const active = phaseIndex(phase);
  const showThinking =
    thinking.length > 0 &&
    (phase === "thinking" || phase === "searching" || phase === "sending" || phase === "answering");

  return (
    <div className="chat-progress">
      {loaderVariant === "metaball" && (
        <svg className="chat-progress-goo-defs" width="0" height="0" aria-hidden>
          <defs>
            <filter id={gooFilterId} x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2.2" result="blur" />
              <feColorMatrix
                in="blur"
                mode="matrix"
                values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 18 -7"
                result="goo"
              />
              <feBlend in="SourceGraphic" in2="goo" />
            </filter>
          </defs>
        </svg>
      )}
      {/* Only the current phase gets the animated loader; done/pending steps stay static dots. */}
      {STAGES.map((stage, i) => {
        let cls = "progress-step";
        if (i < active) cls += " done";
        else if (i === active) cls += " active";
        return (
          <div key={stage.key} className={cls}>
            {i === active ? (
              <span className="progress-loader">
                {loaderVariant === "pathMorph" ? (
                  <ChatProgressPathMorph stage={i} />
                ) : (
                  <ChatProgressMetaball stage={i} filterId={gooFilterId} />
                )}
              </span>
            ) : (
              <span className="progress-dot" />
            )}
            <span className="progress-label">{stage.label}</span>
          </div>
        );
      })}
      {showThinking && (
        <div
          className={
            "chat-progress-thinking" +
            (minimizeThinking && phase === "answering" ? " chat-progress-thinking--min" : "")
          }
        >
          {thinking}
        </div>
      )}
    </div>
  );
}
