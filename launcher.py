"""
Windows-safe launcher — sets SelectorEventLoop BEFORE uvicorn touches asyncio,
then starts the server programmatically.
"""
import asyncio
import sys

# Must happen before any event loop is created.
# Python 3.12 on Windows defaults to ProactorEventLoop which breaks
# the websockets library (AssertionError in _drain_helper).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        ws_ping_interval=None,   # disable library keepalive — app has its own
        ws_ping_timeout=None,
        loop="asyncio",
    )
