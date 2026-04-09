import type { TokenMetrics } from "../types";

interface Props {
  metrics: TokenMetrics | null;
  loading?: boolean;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return n.toLocaleString();
}

export function IndexMetrics({ metrics, loading }: Props) {
  if (loading) return <div className="index-metrics muted">Loading metrics...</div>;
  if (!metrics || metrics.chunk_count === 0) return null;

  return (
    <div className="index-metrics">
      <h3 className="metrics-title">Index Metrics</h3>

      <div className="metrics-grid">
        <div className="metric-item">
          <span className="metric-value">{metrics.chunk_count}</span>
          <span className="metric-label">Chunks</span>
        </div>
        <div className="metric-item">
          <span className="metric-value">{formatNumber(metrics.chunk_tokens)}</span>
          <span className="metric-label">Tokens Used</span>
        </div>
        <div className="metric-item highlight">
          <span className="metric-value">{formatNumber(metrics.tokens_saved)}</span>
          <span className="metric-label">Tokens Saved</span>
        </div>
      </div>

      <div className="metrics-bar-container">
        <div className="metrics-bar-label">
          <span>Chunk tokens vs. raw document tokens</span>
          <span className="metrics-pct">{metrics.savings_pct}% saved</span>
        </div>
        <div className="metrics-bar-track">
          <div
            className="metrics-bar-fill"
            style={{
              width: `${Math.max(2, 100 - metrics.savings_pct)}%`,
            }}
          />
        </div>
        <div className="metrics-bar-legend">
          <span>{formatNumber(metrics.chunk_tokens)} chunk tokens</span>
          <span>{formatNumber(metrics.document_tokens)} raw tokens</span>
        </div>
      </div>
    </div>
  );
}
