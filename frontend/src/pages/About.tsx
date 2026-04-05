const GITHUB_URL = "https://github.com/farawayfound/ChunkyLink";

export function About() {
  return (
    <div className="about-page">
      <h2>About ChunkyLink</h2>

      <div className="about-panel">
        <section className="about-section">
          <h3>What this is</h3>
          <p>
            <strong>ChunkyLink</strong> is a self-hosted{" "}
            <abbr title="Retrieval-Augmented Generation">RAG</abbr> system I built as a portfolio demo: it answers
            questions from an indexed knowledge base instead of guessing from the model alone. The{" "}
            <strong>Ask Me Anything</strong> experience is grounded in a curated corpus (résumé and project narrative);
            signed-in users can also upload and chat with their own documents. The goal is to show how ingestion, NLP
            metadata, retrieval, safety checks, and streaming APIs fit together in a real stack—not a slide-deck
            architecture diagram.
          </p>
        </section>

        <section className="about-section">
          <h3>Where it runs</h3>
          <p>
            This instance is hosted on a small home-lab machine: an <strong>AMD Ryzen 6430U</strong> mini PC with{" "}
            <strong>32&nbsp;GB DDR4</strong> RAM, running Linux with local LLM inference. That setup keeps data on
            hardware I control and keeps the demo honest about latency on modest silicon.
          </p>
        </section>

        <section className="about-section">
          <h3>Architecture (high level)</h3>
          <ul className="about-list">
            <li>
              <strong>Client</strong> — React and TypeScript (Vite); chat consumes server-sent events for streamed
              tokens and phase updates (search vs. generation).
            </li>
            <li>
              <strong>API</strong> — FastAPI (Uvicorn) exposes streaming chat and document workflows; SQLite backs
              lightweight auth and invite codes.
            </li>
            <li>
              <strong>Knowledge base</strong> — Chunks stored as <strong>JSONL</strong> (no separate vector database).
              Retrieval uses chunk search with NLP-enriched metadata; an indexing pipeline classifies content, tags
              entities, deduplicates semantically, and links related chunks.
            </li>
            <li>
              <strong>LLM</strong> — <strong>Ollama</strong> for local inference; the backend streams responses over
              HTTP.
            </li>
            <li>
              <strong>RAG pipeline</strong> — Query handling → retrieval from the KB → <strong>relevance gating</strong>{" "}
              (low-similarity context is refused so the model is less tempted to hallucinate) → prompt assembly →
              streamed answer.
            </li>
            <li>
              <strong>Beyond the web UI</strong> — A <strong>Model Context Protocol (MCP)</strong> server exposes tools
              such as knowledge search, Jira search, and index builds for IDE workflows; optional Jira CSV ingestion can
              target MySQL where that integration is enabled.
            </li>
          </ul>
        </section>

        <section className="about-section">
          <h3>Tech stack</h3>
          <p className="about-tags" aria-label="Technologies">
            Python · FastAPI · Uvicorn · httpx · React · TypeScript · Vite · Ollama · spaCy (
            <code className="monospace">en_core_web_md</code>) · SQLite · JSONL knowledge store · optional MySQL · MCP ·
            systemd (production deploy)
          </p>
        </section>

        <section className="about-section">
          <h3>Source code</h3>
          <p>
            <a className="about-github-link" href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              github.com/farawayfound/ChunkyLink
            </a>
          </p>
        </section>

        <p className="muted about-footnote">
          First-token latency on this hardware is on the order of many seconds—fine for a personal demo, and a useful
          reminder that local RAG is as much an ops and sizing problem as a modeling one.
        </p>
      </div>
    </div>
  );
}
