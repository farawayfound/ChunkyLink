import { useState } from "react";
import { requestAccess } from "../api/client";

interface Props {
  onClose: () => void;
}

export function RequestAccessModal({ onClose }: Props) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setStatus("sending");
    setMessage("");
    setDevCode(null);

    try {
      const data = await requestAccess(email.trim());
      setStatus("sent");
      setMessage(data.message || "Access code sent! Check your email.");
      if (data.code) {
        setDevCode(data.code);
      }
    } catch (err: any) {
      setStatus("error");
      setMessage(err.message || "Something went wrong. Please try again.");
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>

        <h2>Request Access</h2>
        <p className="modal-subtitle">
          Enter your email to receive an access code.
        </p>

        {status === "sent" ? (
          <div className="modal-success">
            <p>{message}</p>
            {devCode && (
              <div className="modal-dev-code">
                <p className="muted">Dev mode — your code:</p>
                <code>{devCode}</code>
              </div>
            )}
            <button onClick={onClose} className="btn btn-primary btn-block">
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <label htmlFor="access-email">Email address</label>
            <input
              id="access-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              autoFocus
              required
            />
            {status === "error" && <p className="error">{message}</p>}
            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={status === "sending" || !email.trim()}
            >
              {status === "sending" ? "Sending..." : "Send Access Code"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
