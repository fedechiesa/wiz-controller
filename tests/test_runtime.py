import asyncio
from collections import Counter
import threading
import unittest

from wiz_controller.lighting import BulbState, UnconfirmedError
from wiz_controller.runtime import LightingRuntime


class RuntimeTests(unittest.TestCase):
    def test_same_ip_is_serialized_and_other_ip_runs_independently(self):
        class Service:
            active = Counter()
            peak = Counter()
            threads = set()
            total_peak = 0

            async def execute(self, ip, action, **kwargs):
                self.threads.add(threading.current_thread().name)
                self.active[ip] += 1
                self.peak[ip] = max(self.peak[ip], self.active[ip])
                self.total_peak = max(self.total_peak, sum(self.active.values()))
                await asyncio.sleep(0.02)
                self.active[ip] -= 1
                return BulbState(True, 70, (145, 45, 255), None)

        service = Service()
        worker = LightingRuntime(service)
        try:
            futures = [worker.submit("bulb1", "ip1", i, "on") for i in range(3)]
            futures.append(worker.submit("bulb2", "ip2", 4, "on"))
            for future in futures:
                future.result(timeout=2)
            self.assertEqual(service.peak["ip1"], 1)
            self.assertEqual(service.total_peak, 2)
            self.assertEqual(service.threads, {"wiz-network"})
            self.assertEqual(worker.results.qsize(), 4)
        finally:
            worker.close()
            worker.thread.join(2)
        self.assertFalse(worker.thread.is_alive())

    def test_errors_reach_ui_queue_without_false_success(self):
        class Service:
            async def execute(self, ip, action, **kwargs):
                if ip == "unconfirmed":
                    raise UnconfirmedError(BulbState(False, 15, None, 2700))
                raise TimeoutError()

        worker = LightingRuntime(Service())
        try:
            worker.submit("bulb1", "offline", 1, "on").result(2)
            failed = worker.results.get_nowait()
            self.assertFalse(failed.reachable)
            self.assertIsNone(failed.state)
            self.assertIn("Tiempo", failed.error)
            worker.submit("bulb2", "unconfirmed", 2, "on").result(2)
            mismatch = worker.results.get_nowait()
            self.assertTrue(mismatch.reachable)
            self.assertIsNotNone(mismatch.error)
            self.assertFalse(mismatch.state.power)
        finally:
            worker.close()
            worker.thread.join(2)
