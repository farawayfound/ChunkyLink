import { useRef, useEffect, useState, useCallback } from "react";
import { useChat } from "../hooks/useChat";
import { ChatMessage } from "../components/ChatMessage";
import { ChatInput } from "../components/ChatInput";
import { ChatProgress } from "../components/ChatProgress";
import { RequestAccessModal } from "../components/RequestAccessModal";
import { getChatSuggestions } from "../api/client";

export function AskMeAnything() {
  const { messages, streaming, phase, send, clear } = useChat("/chat/ask");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showAccessModal, setShowAccessModal] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    getChatSuggestions()
      .then((data) => {
        const pool = data.suggestions || [];
        const shuffled = pool.sort(() => Math.random() - 0.5);
        setSuggestions(shuffled.slice(0, 4));
      })
      .catch(() => {
        setSuggestions(["Tell me about your professional background"]);
      });
  }, []);

  // Detect rate limit from chat error messages (429 response)
  useEffect(() => {
    if (rateLimited) return;
    const lastMsg = messages[messages.length - 1];
    if (
      lastMsg?.role === "assistant" &&
      (lastMsg.content.includes("rate_limited") || lastMsg.content.includes("(429)"))
    ) {
      setRateLimited(true);
      setShowAccessModal(true);
    }
  }, [messages, rateLimited]);

  const handleSend = useCallback(
    (query: string) => {
      if (rateLimited) {
        setShowAccessModal(true);
        return;
      }
      send(query);
    },
    [send, rateLimited],
  );

  return (
    <div className="chat-page">
      <div className="chat-header">
        <h2>Ask Me Anything</h2>
        {messages.length > 0 && (
          <button onClick={clear} className="btn btn-sm">Clear</button>
        )}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask anything about my background, skills, or projects.</p>
            {suggestions.length > 0 && (
              <div className="suggestions">
                {suggestions.map((q, i) => (
                  <button key={i} onClick={() => handleSend(q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {streaming && <ChatProgress phase={phase} />}
        {rateLimited && !showAccessModal && (
          <div className="rate-limit-banner">
            <p>You've reached the free question limit.</p>
            <button
              onClick={() => setShowAccessModal(true)}
              className="btn btn-sm btn-primary"
            >
              Request Access to Continue
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <ChatInput
        onSend={handleSend}
        disabled={streaming}
        placeholder={rateLimited ? "Request access to ask more questions..." : "Ask about my experience..."}
      />

      {showAccessModal && (
        <RequestAccessModal onClose={() => setShowAccessModal(false)} />
      )}
    </div>
  );
}
