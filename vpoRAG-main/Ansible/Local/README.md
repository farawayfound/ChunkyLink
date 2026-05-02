# Ansible/Local — Local Machine Setup

Sets up vpoRAG on a Windows developer workstation:
- Creates `.venv` at the repo root
- Installs all dependencies from `requirements.txt`
- Downloads the `en_core_web_md` spaCy model
- Renders `indexers/config.py` with your local paths
- Renders `Searches/config.ps1` with your local paths

## Windows (native) — use Setup/Local/setup_local.py

Ansible requires Unix-only syscalls (`fcntl`) and cannot run on native Windows
Python. Use the equivalent Python script in `Setup/Local/` instead:

```powershell
# Minimal — auto-detects repo root from script location
python Setup\Local\setup_local.py

# Full — specify all paths explicitly
python Setup\Local\setup_local.py `
    --repo-root  "C:\Users\you\repos\vpo_rag" `
    --src-dir    "C:\Users\you\Documents\VPO_Docs" `
    --tesseract  "C:\Program Files\Tesseract-OCR" `
    --search-mode Local `
    --jira-source csv

# Re-render config files only (skip venv rebuild and spaCy download)
python Setup\Local\setup_local.py --skip-venv --skip-spacy
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--repo-root` | parent of `Ansible/Local/` | Absolute path to repo root |
| `--src-dir` | `<repo>/source_docs` | Source documents directory |
| `--tesseract` | auto-detect | Tesseract install directory |
| `--search-mode` | `Local` | `Local` or `MCP` |
| `--jira-source` | `csv` | `csv`, `mysql`, or `sql` |
| `--python` | `python` | Python executable for venv creation |
| `--skip-venv` | off | Skip venv creation and pip install |
| `--skip-spacy` | off | Skip spaCy model download |
| `--skip-config` | off | Skip rendering config files |

## WSL — use the Ansible playbook

If you have WSL with Ansible installed:

```bash
cd Ansible/Local
ansible-playbook -i inventory.ini site.yml \
    -e "repo_root=/mnt/c/Users/you/repos/vpo_rag" \
    -e "indexer_src_dir=/mnt/c/Users/you/Documents/VPO_Docs"
```

## Verify the setup

```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Check spaCy model loaded
python -c "import spacy; nlp = spacy.load('en_core_web_md'); print('spaCy OK')"

# Run indexer test suite
cd indexers
python tests/test_json_indexer.py
```
