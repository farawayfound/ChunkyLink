import { useState, useCallback, useEffect } from "react";
import { createChatSession, listChatSessions, getChatSession, deleteChatSession } from "../api/client";
import type { ChatMessage } from "../types";

export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export function useSession() {
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const data = await listChatSessions();
      setSessions(data.sessions);
    } catch (err) {
      console.error("Failed to load sessions:", err);
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const createSession = useCallback(async () => {
    try {
      const data = await createChatSession();
      const newSessionId = data.session_id;
      setCurrentSessionId(newSessionId);
      // Reload sessions to include the new one
      await loadSessions();
      return newSessionId;
    } catch (err) {
      console.error("Failed to create session:", err);
      return null;
    }
  }, [loadSessions]);

  const selectSession = useCallback(async (sessionId: string) => {
    setLoadingSession(true);
    try {
      const data = await getChatSession(sessionId);
      setCurrentSessionId(sessionId);
      return data;
    } catch (err) {
      console.error("Failed to load session:", err);
      return null;
    } finally {
      setLoadingSession(false);
    }
  }, []);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteChatSession(sessionId);
        if (currentSessionId === sessionId) {
          setCurrentSessionId(null);
        }
        // Reload sessions
        await loadSessions();
        return true;
      } catch (err) {
        console.error("Failed to delete session:", err);
        return false;
      }
    },
    [currentSessionId, loadSessions],
  );

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  return {
    currentSessionId,
    sessions,
    loadingSession,
    loadingSessions,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
  };
}
