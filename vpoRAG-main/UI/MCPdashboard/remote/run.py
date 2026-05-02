# -*- coding: utf-8 -*-
"""Remote entry point — runs the dashboard on the MCP server, reading the log directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base.app_factory import create_app
from remote.log_reader import LocalLogReader

app = create_app(LocalLogReader())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
