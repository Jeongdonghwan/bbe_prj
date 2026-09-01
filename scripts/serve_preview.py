"""Temporary customer-preview server: waitress on 0.0.0.0:8034, debug features off.

    python scripts/serve_preview.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FLASK_DEBUG"] = "0"

from waitress import serve  # noqa: E402

from app import create_app  # noqa: E402

app = create_app()
app.debug = False
if __name__ == "__main__":
    print("preview server: http://0.0.0.0:8034")
    serve(app, host="0.0.0.0", port=8034, threads=8)
