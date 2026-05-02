# vpoRAG UI — Agent Reference

## Sub-applications

### Indexer (port 5000)
Web UI for managing the local knowledge base index.
```
UI/Indexer/RUN_UI.bat   →  http://localhost:5000
```
See `UI/Indexer/Agents.md` for full feature reference.

### MCP Dashboard (port 5001)
Web UI for viewing MCP server access logs, usage trends, and errors.

**Always-on (preferred):** Deployed as a systemd service on the MCP server — accessible from any LAN machine without launching anything locally.
```
http://192.168.1.29:5001
```

**Local fallback:** Run on Windows to access the dashboard when off-LAN or for development.
```
UI/MCPdashboard/RUN_DASHBOARD.bat   →  http://localhost:5001
```
Local mode reads `mcp_access.log` via SSH (`~/.ssh/vporag_key`, owner-only permissions required).

See `UI/MCPdashboard/README.md` for architecture, deployment, and update instructions.

## Notes
- The MCP Dashboard is LAN-accessible via the server deployment; the Indexer UI remains localhost-only
- Both UIs are independent; they can run simultaneously on their respective ports
- Neither UI is authenticated — access is implicitly restricted to LAN
