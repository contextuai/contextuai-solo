"""
ContextuAI Solo Backend — PyInstaller entry point.

Launches the FastAPI app via uvicorn with CLI args for host/port.
"""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="ContextuAI Solo Backend")
    parser.add_argument("--port", type=int, default=18741)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    os.environ["CONTEXTUAI_MODE"] = "desktop"
    os.environ["ENVIRONMENT"] = "desktop"

    # When running from a PyInstaller bundle, _MEIPASS points to the
    # temporary extraction directory (onefile) or the _internal dir
    # (onedir).  We need it on sys.path so that uvicorn can resolve
    # the "app" module by name.
    if getattr(sys, "_MEIPASS", None):
        base = sys._MEIPASS
        if base not in sys.path:
            sys.path.insert(0, base)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        if base not in sys.path:
            sys.path.insert(0, base)

    agent_lib = os.path.join(base, "agent-library")
    if os.path.isdir(agent_lib):
        os.environ["AGENT_LIBRARY_PATH"] = agent_lib

    import uvicorn
    from app import app  # noqa: F401 — ensure PyInstaller includes it

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
