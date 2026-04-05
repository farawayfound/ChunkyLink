import { useState, useCallback, useRef } from "react";
import { streamChat } from "../api/client";
import type { ChatMessage } from "../types";

export type ChatPhase = "idle" | "sending" | "searching" | "thinking" | "answering";

export function useChat(endpoint: "/chat/ask" | "/chat/documents" = "/chat/ask") {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [phase, setPhase] = useState<ChatPhase>("idle");
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (query: string, extra?: Record<string, unknown>) => {
      const userMsg: ChatMessage = { role: "user", content: query };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setPhase("sending");

      const assistantMsg: ChatMessage = { role: "assistant", content: "", thinking: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        const body: Record<string, unknown> = { query, ...extra };
        if (endpoint === "/chat/documents") {
          body.messages = [...messages, userMsg].map((m) => ({
            role: m.role,
            content: m.content,
          }));
        }

        for await (const event of streamChat(endpoint, body)) {
          if (event.phase) {
            if (event.phase === "search") setPhase("searching");
            else if (event.phase === "generate") setPhase("thinking");
            else if (event.phase === "answering") setPhase("answering");
          }
          if (event.thinking) {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  thinking: (last.thinking || "") + event.thinking,
                };
              }
              return updated;
            });
          }
          if (event.text) {
            setPhase("answering");
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, content: last.content + event.text };
              }
              return updated;
            });
          }
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            const base = last.content.trim();
            updated[updated.length - 1] = {
              ...last,
              content: base
                ? `${last.content}\n\n[Error: ${detail}]`
                : `Sorry, something went wrong.\n\n${detail}`,
            };
          }
          return updated;
        });
      } finally {
        setStreaming(false);
        setPhase("idle");
      }
    },
    [endpoint, messages],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setPhase("idle");
  }, []);

  return { messages, streaming, phase, send, clear };
}
