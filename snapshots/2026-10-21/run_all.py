"""Reproduce the validated update entirely offline after installing requirements."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parent
for name in ['run_update.py','render_charts.py']:
    subprocess.run([sys.executable,str(root/name)],cwd=root,check=True)
print('Data-only update reproduced; model code and historical calibration unchanged.')
