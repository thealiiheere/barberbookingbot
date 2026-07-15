"""
Minimal HTTP endpoint so an external uptime monitor (e.g. UptimeRobot,
SimpleMonitor, or a simple curl-based check) can confirm the bot process
AND its database connection are both alive - not just that the process
exists, but that it can actually reach Postgres.

Runs alongside the bot's polling loop in the same asyncio event loop; no
separate server or process needed.
"""

import logging

import asyncpg
from aiohttp import web

logger = logging.getLogger(__name__)


async def _health(request: web.Request) -> web.Response:
    pool: asyncpg.Pool = request.app["db_pool"]
    try:
        await pool.fetchval("SELECT 1;")
    except Exception:
        logger.exception("Health check DB probe failed")
        return web.json_response({"status": "db_error"}, status=503)
    return web.json_response({"status": "ok"})


async def start_health_server(pool: asyncpg.Pool, port: int) -> web.AppRunner:
    """Call once from main.py, after the DB pool exists. Point your uptime
    monitor at http://<server-ip>:<port>/health - it should return
    {"status": "ok"} with a 200, or a 503 if the database is unreachable."""
    app = web.Application()
    app["db_pool"] = pool
    app.router.add_get("/health", _health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Health check server listening on :%s/health", port)
    return runner