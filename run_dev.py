"""
Local dev server on Windows when `py -m uvicorn` fails with WinError 10013
(ProactorEventLoop, blocked port, or uvicorn's second bind / httptools).

Run from project root (rcaagent-env):
  py -3.11 run_dev.py
  py -3.11 run_dev.py --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import sys


def _can_bind(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _pick_port(host: str, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    if sys.platform != "win32":
        return 8000
    for candidate in (18765, 28765, 34567, 41729, 49876):
        if _can_bind(host, candidate):
            return candidate
    return 18765


def _uvicorn_run_windows(*, app: str, host: str, port: int, reload: bool) -> None:
    """Selector loop + h11 (avoid Proactor socketpair issues; fd= is broken on Windows in newer uvicorn)."""
    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="asyncio",
        http="h11",
        reload=reload,
    )


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    parser = argparse.ArgumentParser(description="RCAAgent-Env dev server")
    parser.add_argument(
        "--host",
        default="127.0.0.1" if sys.platform == "win32" else "0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port (Windows default: first free among 18765, 28765, ... if not set)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable reload (can fail on Windows; omit if you see socket errors)",
    )
    args = parser.parse_args()
    reload = args.reload and sys.platform != "win32"

    port = _pick_port(args.host, args.port)
    if args.port is None and sys.platform == "win32":
        print(f"RCAAgent-Env: using port {port} (8080 is often reserved on Windows).")
    print()
    print("  Browser URL (use HTTP, not HTTPS; match this port exactly):")
    print(f"    http://{args.host}:{port}/")
    print(f"    http://{args.host}:{port}/docs")
    if args.host == "127.0.0.1":
        print("  If 'localhost' fails, keep using 127.0.0.1 (IPv6 localhost may not be listening).")
    print("  Wait for: INFO: Uvicorn running on http://...")
    print("  If the process exits with an error, nothing is listening — fix the error first.")
    print()

    if sys.platform == "win32":
        _uvicorn_run_windows(app="server.app:app", host=args.host, port=port, reload=reload)
    else:
        uvicorn.run("server.app:app", host=args.host, port=port, reload=reload)


if __name__ == "__main__":
    main()
