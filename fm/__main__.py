"""Entry point for Football Manager.

Usage:
    uv run python -m fm          # Launch TUI
    uv run python -m fm --api    # Launch FastAPI server
    uv run python -m fm --train  # Train ML models
"""
from __future__ import annotations

import sys


def main():
    """Launch the appropriate interface."""
    if "--api" in sys.argv:
        import uvicorn
        from fm.api.app import app
        port = 8000
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        uvicorn.run(app, host="0.0.0.0", port=port)
    elif "--train" in sys.argv:
        from fm.engine.ml.model_store import train_all_models
        print("Training all ML models...")
        train_all_models()
        print("Done! Models saved to data/models/")
    else:
        from fm.ui.app import FootballManagerApp
        app = FootballManagerApp()
        app.run()


if __name__ == "__main__":
    main()
