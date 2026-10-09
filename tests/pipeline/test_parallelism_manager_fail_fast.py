import threading
import unittest

from semantica.pipeline.parallelism_manager import ParallelismManager, Task


class PermanentFailure(RuntimeError):
    retryable = False


class TestPermanentFailureDispatch(unittest.TestCase):
    def test_stops_submitting_after_permanent_failure(self):
        release = threading.Event()
        started = threading.Event()
        calls = []

        def fail():
            started.wait(timeout=2)
            calls.append("fail")
            release.set()
            raise PermanentFailure("bad request")

        def in_flight():
            calls.append("in-flight")
            started.set()
            release.wait(timeout=2)

        def should_not_start():
            calls.append("queued")

        results = ParallelismManager(max_workers=2).execute_parallel(
            [Task("fail", fail), Task("in-flight", in_flight), Task("queued", should_not_start)],
            fail_fast_permanent=True,
        )

        self.assertEqual(set(calls), {"fail", "in-flight"})
        self.assertEqual({result.task_id for result in results}, {"fail", "in-flight"})
        self.assertTrue(next(result for result in results if result.task_id == "fail").error)

    def test_retryable_failure_keeps_dispatching(self):
        calls = []

        def retryable():
            calls.append("retryable")
            raise RuntimeError("temporary")

        def success():
            calls.append("success")

        results = ParallelismManager(max_workers=1).execute_parallel(
            [Task("retryable", retryable), Task("success", success)],
            fail_fast_permanent=True,
        )

        self.assertEqual(calls, ["retryable", "success"])
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
