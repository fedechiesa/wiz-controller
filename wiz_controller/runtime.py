"""One asyncio worker. Tk consumes a thread-safe queue from its own thread."""
import asyncio
from dataclasses import dataclass
import logging
from queue import Queue
import threading

from .lighting import BulbState, LightingService, UnconfirmedError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Result:
    bulb_id: str
    ip: str
    token: int
    action: str
    state: BulbState | None = None
    error: str | None = None
    reachable: bool = False


class LightingRuntime:
    def __init__(self, service=None):
        self.service = service or LightingService()
        self.results = Queue()
        self.loop = asyncio.new_event_loop()
        self._locks = {}
        self._closed = False
        self.thread = threading.Thread(target=self._run, name="wiz-network", daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def submit(self, bulb_id, ip, token, action, **kwargs):
        if self._closed:
            return
        return asyncio.run_coroutine_threadsafe(self._execute(bulb_id, ip, token, action, kwargs), self.loop)

    async def _execute(self, bulb_id, ip, token, action, kwargs):
        lock = self._locks.setdefault(ip, asyncio.Lock())
        async with lock:
            try:
                state = await self.service.execute(ip, action, **kwargs)
                self.results.put(Result(bulb_id, ip, token, action, state, reachable=True))
            except UnconfirmedError as error:
                LOGGER.warning("Unconfirmed %s on %s", action, ip)
                self.results.put(Result(bulb_id, ip, token, action, error.state, str(error), True))
            except Exception as error:
                LOGGER.warning("%s failed on %s: %s", action, ip, error, exc_info=True)
                message = "Tiempo de espera agotado. Revisá la IP y la red local." if isinstance(error, TimeoutError) else str(error)
                self.results.put(Result(bulb_id, ip, token, action, error=message or type(error).__name__))

    def close(self):
        if not self._closed:
            self._closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)
