import ast
from pathlib import Path
bad=[]
for p in Path(__file__).parent.rglob("*.py"):
    if ".venv" in p.parts: continue
    try: ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e: bad.append(f"{p}: {e}")
if bad: print("\n".join(bad)); raise SystemExit(1)
print("Python syntax validation passed.")
