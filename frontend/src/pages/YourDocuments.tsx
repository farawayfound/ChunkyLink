import { useEffect, useRef, useCallback } from "react";
import { useDocuments } from "../hooks/useDocuments";
import { useChat } from "../hooks/useChat";
import { UploadZone } from "../components/UploadZone";
import { DocumentCard } from "../components/DocumentCard";
import { ChatMessage } from "../components/ChatMessage";
import { ChatInput } from "../components/ChatInput";
import { ChatProgress } from "../components/ChatProgress";
import { ChunkingConfig } from "../components/ChunkingConfig";
import { IndexMetrics } from "../components/IndexMetrics";

export function YourDocuments() {
  const {
    documents, loading, indexStatus,
    chunkingConfig, metrics, metricsLoading,
    refresh, upload, remove,
    startIndex, refreshIndex,
    refreshConfig, saveConfig, refreshMetrics,
  } = useDocuments();
  const { messages, streaming, phase, send, clear } = useChat("/chat/documents");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    refresh();
    refreshIndex();
    refreshConfig();
    refreshMetrics();
  }, [refresh, refreshIndex, refreshConfig, refreshMetrics]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const jobStatus = indexStatus?.job?.status || "idle";

  const handleStartIndex = useCallback(async () => {
    await startIndex();
    refreshMetrics();
  }, [startIndex, refreshMetrics]);

  return (
    <div className="documents-page">
      <div className="documents-sidebar">
        <h2>Your Documents</h2>
        <UploadZone onUpload={upload} />

        <div className="document-list">
          {loading && <p>Loading...</p>}
          {!loading && documents.length === 0 && <p className="muted">No documents uploaded yet.</p>}
          {documents.map((doc) => (
            <DocumentCard key={doc.filename} doc={doc} onDelete={remove} />
          ))}
        </div>

        <ChunkingConfig
          config={chunkingConfig}
          onSave={saveConfig}
          disabled={jobStatus === "running"}
        />

        <IndexMetrics metrics={metrics} loading={metricsLoading} />

        <div className="index-controls">
          <button
            className="btn btn-primary btn-block"
            onClick={handleStartIndex}
            disabled={jobStatus === "running" || documents.length === 0}
          >
            {jobStatus === "running" ? "Indexing..." : "Build Index"}
          </button>
          {indexStatus?.last_run && (
            <p className="muted">
              Last indexed: {indexStatus.last_run.chunks} chunks from {indexStatus.last_run.files} files
            </p>
          )}
        </div>
      </div>

      <div className="documents-chat">
        <div className="chat-header">
          <h2>Chat with Your Documents</h2>
          {messages.length > 0 && (
            <button onClick={clear} className="btn btn-sm">Clear</button>
          )}
        </div>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <p>Upload and index documents, then ask questions about them.</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessage key={i} message={msg} />
          ))}
          {streaming && <ChatProgress phase={phase} />}
          <div ref={bottomRef} />
        </div>

        <ChatInput
          onSend={send}
          disabled={streaming}
          placeholder="Ask about your documents..."
        />
      </div>
    </div>
  );
}
