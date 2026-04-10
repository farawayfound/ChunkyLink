import { useState, useCallback } from "react";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  getDocumentStats,
  buildIndex,
  getIndexStatus,
  getChunkingConfig,
  updateChunkingConfig,
  getTokenMetrics,
  getAgentConfig,
  updateAgentConfig,
} from "../api/client";
import type { Document, IndexStatus, ChunkingConfig, TokenMetrics } from "../types";

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null);
  const [chunkingConfig, setChunkingConfig] = useState<ChunkingConfig | null>(null);
  const [metrics, setMetrics] = useState<TokenMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [agentConfig, setAgentConfig] = useState<{
    system_prompt: string;
    system_rules: string;
    default_system_prompt: string;
    default_system_rules: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDocuments();
      setDocuments(data.documents);
    } catch {
      // no-op if not authenticated
    } finally {
      setLoading(false);
    }
  }, []);

  const upload = useCallback(
    async (file: File) => {
      await uploadDocument(file);
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (filename: string) => {
      await deleteDocument(filename);
      await refresh();
    },
    [refresh],
  );

  const startIndex = useCallback(async () => {
    await buildIndex();
    await refreshIndex();
  }, []);

  const refreshIndex = useCallback(async () => {
    try {
      const status = await getIndexStatus();
      setIndexStatus(status);
    } catch {
      // no-op
    }
  }, []);

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await getChunkingConfig();
      setChunkingConfig(cfg);
    } catch {
      // no-op
    }
  }, []);

  const saveConfig = useCallback(async (config: Partial<ChunkingConfig>) => {
    const saved = await updateChunkingConfig(config as Record<string, unknown>);
    setChunkingConfig(saved);
  }, []);

  const refreshMetrics = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const m = await getTokenMetrics();
      setMetrics(m);
    } catch {
      // no-op
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const refreshAgentConfig = useCallback(async () => {
    try {
      const cfg = await getAgentConfig();
      setAgentConfig(cfg);
    } catch {
      // no-op
    }
  }, []);

  const saveAgentConfig = useCallback(async (config: Record<string, unknown>) => {
    const saved = await updateAgentConfig(config);
    // Re-fetch to get defaults too
    await refreshAgentConfig();
    return saved;
  }, [refreshAgentConfig]);

  return {
    documents, loading, indexStatus,
    chunkingConfig, metrics, metricsLoading,
    agentConfig,
    refresh, upload, remove,
    startIndex, refreshIndex,
    refreshConfig, saveConfig, refreshMetrics,
    refreshAgentConfig, saveAgentConfig,
  };
}
