import subprocess, sys
from pathlib import Path

with open(Path(__file__).parent.parent.parent / 'requirements.txt') as f:
    for line in f:
        pkg = line.strip().split('[')[0].split('==')[0]
        result = subprocess.run([sys.executable, '-m', 'pip', 'show', pkg], 
                              capture_output=True)
        status = '✓ installed' if result.returncode == 0 else '✗ missing'
        print(f'{pkg}: {status}')
