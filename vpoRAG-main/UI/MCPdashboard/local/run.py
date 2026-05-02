# -*- coding: utf-8 -*-
"""Local entry point — runs the dashboard on Windows, reading the log via SSH."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base.app_factory import create_app
from local.log_reader import SshLogReader

app = create_app(SshLogReader())

if __name__ == '__main__':
    print("=" * 60)
    print("vpoRAG MCP Dashboard  [local / SSH mode]")
    print("MCP Host:  vpomac@192.168.1.29")
    print("Starting:  http://localhost:5001")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5001, debug=True)
