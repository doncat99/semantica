"""
Parallelism Manager Module

This module provides parallel execution management for pipeline tasks and operations,
supporting thread-based and process-based parallelism with load balancing and
performance optimization.

Key Features:
    - Parallel task execution and coordination
    - Resource allocation and scheduling
    - Load balancing and optimization
    - Performance monitoring and tuning
    - Error handling and recovery
    - Thread and process pool execution
    - Task priority management

Main Classes:
    - ParallelismManager: Parallelism management system
    - ParallelExecutor: Parallel execution coordinator
    - Task: Dataclass for parallel task definition
    - ParallelExecutionResult: Dataclass for parallel execution results

Example Usage:
    >>> from semantica.pipeline import ParallelismManager, Task
    >>> manager = ParallelismManager(max_workers=4)
    >>> tasks = [Task("task1", handler, args), Task("task2", handler2, args2)]
    >>> results = manager.execute_parallel(tasks)

Author: Semantica Contributors
License: MIT
"""

import threading
import time
import math
import importlib
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .pipeline_builder import Pipeline, PipelineStep


@dataclass
class Task:
    """Parallel task definition."""

    task_id: str
    handler: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    max_attempts: int = 1
    on_retry: Optional[Callable] = None


@dataclass
class ParallelExecutionResult:
    """Parallel execution result."""

    task_id: str
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    attempts: int = 1


def _execute_task(task: Task) -> ParallelExecutionResult:
    started = time.perf_counter()
    for attempt in range(1, max(1, task.max_attempts) + 1):
        try:
            return ParallelExecutionResult(task_id=task.task_id, success=True,
                                           result=task.handler(*task.args, **task.kwargs),
                                           execution_time=time.perf_counter() - started, attempts=attempt)
        except Exception as error:
            from ..semantic_extract.providers import BaseProvider
            chain = list(BaseProvider._error_chain(error))
            transient = not BaseProvider._is_permanent_failure(error) and any(
                getattr(cause, 'retryable', None) is True for cause in chain)
            if not transient or attempt >= task.max_attempts:
                return ParallelExecutionResult(task_id=task.task_id, success=False, error=error,
                                               execution_time=time.perf_counter() - started, attempts=attempt)
            delay_ms = max([1000 * attempt] + [delay for cause in chain
                           if type(delay := getattr(cause, 'retry_after_ms', None)) is int and delay >= 0])
            if task.on_retry:
                task.on_retry(attempt + 1, delay_ms, error)
            time.sleep(delay_ms / 1000)


class _TransportFailure(Exception):
    pass


def _write_json_value(path, value, limit, check=lambda: None, invocation_args=None):
    """Write only exact JSON types, incrementally and without custom hooks/copies."""
    remaining = limit
    nodes = 0
    with open(path, "wb") as stream:
        def write(text):
            nonlocal remaining
            check()
            encoded = text.encode("utf-8")
            remaining -= len(encoded)
            if remaining < 0:
                raise _TransportFailure("limit")
            stream.write(encoded)

        def visit(item, depth=0):
            nonlocal nodes
            check()
            nodes += 1
            if nodes > limit or depth > 64:
                raise _TransportFailure("limit")
            kind = type(item)
            if kind is str:
                if len(item) > limit:
                    raise _TransportFailure("limit")
                write('"')
                for offset in range(0, len(item), 16384):
                    write(json.dumps(item[offset:offset + 16384], ensure_ascii=True)[1:-1])
                write('"')
            elif item is None or kind is bool or kind is int or kind is float:
                try:
                    write(json.dumps(item, allow_nan=False))
                except (ValueError, OverflowError) as error:
                    raise _TransportFailure("contract") from error
            elif kind is list or (kind is tuple and item is invocation_args):
                write("[")
                for index, child in enumerate(item):
                    if index:
                        write(",")
                    visit(child, depth + 1)
                write("]")
            elif kind is dict:
                write("{")
                for index, (key, child) in enumerate(item.items()):
                    if type(key) is not str:
                        raise _TransportFailure("contract")
                    if index:
                        write(",")
                    visit(key, depth + 1)
                    write(":")
                    visit(child, depth + 1)
                write("}")
            else:
                raise _TransportFailure("contract")
        visit(value)


def _isolated_file_operation(directory, parent_pid, max_rss_bytes, transport_limit):
    """Single native worker entry: no executable object deserialization."""
    import psutil
    current = psutil.Process()
    parent = psutil.Process(parent_pid)
    parent_created = parent.create_time()

    def watch():
        try:
            while True:
                if (not parent.is_running() or parent.status() == psutil.STATUS_ZOMBIE
                        or parent.create_time() != parent_created):
                    os._exit(73)
                time.sleep(.05)
        except Exception:
            os._exit(73)

    threading.Thread(target=watch, daemon=True).start()
    if current.memory_info().rss > max_rss_bytes:
        os._exit(72)
    directory = Path(directory)
    try:
        descriptor = json.loads((directory / "input").read_bytes())
        handler = importlib.import_module(descriptor["module"])
        for part in descriptor["qualname"].split("."):
            handler = getattr(handler, part)
        result = handler(*descriptor["args"], **descriptor["kwargs"])
        try:
            _write_json_value(directory / "result", result, transport_limit)
        except _TransportFailure as error:
            (directory / "failure").write_text("output_" + str(error))
            return
    except Exception as error:
        # Error strings are bounded as well; never serialize exception objects.
        (directory / "failure").write_text((type(error).__name__ + ": " + str(error))[:4096])
        return
    (directory / "complete").touch()


class ParallelismManager:
    """
    Parallelism management system.

    • Parallel task execution and coordination
    • Resource allocation and scheduling
    • Load balancing and optimization
    • Performance monitoring and tuning
    • Error handling and recovery
    • Advanced parallelism strategies
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize parallelism manager.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - max_workers: Maximum parallel workers
                - use_processes: Use processes instead of threads
        """
        self.logger = get_logger("parallelism_manager")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.max_workers = self.config.get("max_workers", 4)
        self.use_processes = self.config.get("use_processes", False)

        self.executor: Optional[ThreadPoolExecutor] = None
        self.process_executor: Optional[ProcessPoolExecutor] = None
        self.lock = threading.Lock()

    def execute_isolated_task(self, task: Task, *, timeout_seconds: float,
                              max_rss_bytes: int, cancellation=None,
                              max_transport_bytes: int = 16 * 1024**2):
        """Run an importable handler with bounded JSON input/output and reaping.

        JSON types are exact (no object reducers or custom encoders). The caller
        retains its existing objects. The RSS budget includes the calling process
        and this operation's worker tree throughout transport and execution.
        Sampling runs every 50ms; this is not an OS hard ceiling.
        """
        if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0
                or type(max_rss_bytes) is not int or max_rss_bytes <= 0
                or type(max_transport_bytes) is not int or max_transport_bytes <= 0):
            raise ValidationError("isolated task requires positive finite resource limits")

        def failure(reason):
            return ProcessingError("isolated task failed: " + reason,
                processing_context={"task_id": task.task_id, "reason": reason})

        deadline = time.monotonic() + timeout_seconds
        try:
            import psutil
            parent = psutil.Process()
        except Exception as error:
            raise failure("monitor") from error
        worker = None
        next_memory_check = 0

        def check(*, force_memory=False):
            nonlocal next_memory_check
            if cancellation is not None and cancellation.is_set():
                raise failure("cancelled")
            now = time.monotonic()
            if now >= deadline:
                raise failure("deadline")
            if force_memory or now >= next_memory_check:
                next_memory_check = now + .05
                try:
                    rss = parent.memory_info().rss
                    if worker is not None:
                        try:
                            rss += worker.memory_info().rss
                            for descendant in worker.children(recursive=True):
                                try:
                                    rss += descendant.memory_info().rss
                                except psutil.NoSuchProcess:
                                    pass
                        except psutil.NoSuchProcess:
                            pass
                except psutil.Error as error:
                    raise failure("monitor") from error
                if rss > max_rss_bytes:
                    raise failure("memory")

        check(force_memory=True)
        if type(task.handler) not in (types.FunctionType, types.BuiltinFunctionType, type):
            raise failure("startup")
        module = getattr(task.handler, "__module__", None)
        qualname = getattr(task.handler, "__qualname__", None)
        if (type(module) is not str or type(qualname) is not str
                or not module or not qualname or module == "__main__"
                or "<" in qualname or type(task.args) is not tuple
                or type(task.kwargs) is not dict):
            raise failure("startup")
        # Only the outer invocation tuple is structural; nested tuples are rejected
        # rather than silently changing handler argument semantics.
        descriptor = {"module": module, "qualname": qualname,
                      "args": task.args, "kwargs": task.kwargs}
        process = None
        with tempfile.TemporaryDirectory(prefix="semantica-operation-") as directory:
            directory = Path(directory)
            try:
                _write_json_value(directory / "input", descriptor, max_transport_bytes, check, task.args)
            except _TransportFailure as error:
                raise failure("input_" + str(error)) from error
            check()
            # Startup arguments contain only small primitive strings. In particular
            # Popen never pickles task args/handler/result on the caller thread.
            command = [sys.executable, "-B", "-c",
                "from semantica.pipeline.parallelism_manager import _isolated_file_operation; "
                "import sys; _isolated_file_operation(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))",
                str(directory), str(os.getpid()), str(max_rss_bytes), str(max_transport_bytes)]
            try:
                try:
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as error:
                    raise failure("startup") from error
                try:
                    import psutil
                    worker = psutil.Process(process.pid)
                except Exception as error:
                    raise failure("monitor") from error
                while process.poll() is None:
                    check(force_memory=True)
                    time.sleep(.05)
                check(force_memory=True)
                if process.wait() != 0:
                    raise failure({72: "memory", 73: "parent_exit"}.get(process.returncode, "child_exit"))
                if (directory / "failure").exists():
                    raise failure((directory / "failure").read_text()[:4096])
                if not (directory / "complete").exists():
                    raise failure("transport")
                result_path = directory / "result"
                if result_path.stat().st_size > max_transport_bytes:
                    raise failure("output_limit")
                try:
                    result = json.loads(result_path.read_bytes())
                except Exception as error:
                    raise failure("transport") from error
                check(force_memory=True)
                return result
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    def execute_parallel(
        self, tasks: List[Task], pipeline_id: Optional[str] = None, **options
    ) -> List[ParallelExecutionResult]:
        """
        Execute tasks in parallel.

        Args:
            tasks: List of tasks to execute
            pipeline_id: Optional pipeline ID for progress tracking
            **options: Additional options

        Returns:
            List of execution results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ParallelismManager",
            message=f"Executing {len(tasks)} tasks in parallel",
            pipeline_id=pipeline_id,
        )

        try:
            if not tasks:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="completed", message="No tasks to execute"
                )
                return []

            # Sort by priority
            self.progress_tracker.update_tracking(
                tracking_id, message="Sorting tasks by priority..."
            )
            sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)

            # Execute tasks
            self.progress_tracker.update_tracking(
                tracking_id,
                message=f"Executing tasks using {'processes' if self.use_processes else 'threads'}...",
            )
            if self.use_processes:
                results = self._execute_with_processes(sorted_tasks, **options)
            else:
                results = self._execute_with_threads(sorted_tasks, **options)

            success_count = sum(1 for r in results if r.success)
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Executed {len(tasks)} tasks: {success_count} succeeded, {len(tasks) - success_count} failed",
            )
            return results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _execute_with_threads(self, tasks: List[Task], **options) -> List[ParallelExecutionResult]:
        """Execute tasks using the same timed task primitive as process execution."""
        if options.get("fail_fast", False) or options.get("fail_fast_permanent", False):
            return self._execute_with_threads_fail_fast(tasks, options)
        with ThreadPoolExecutor(max_workers=options.get("max_workers", self.max_workers)) as executor:
            futures = [executor.submit(_execute_task, task) for task in tasks]
            return [future.result() for future in as_completed(futures)]

    @staticmethod
    def _is_permanent_failure(error: Exception) -> bool:
        from ..semantic_extract.providers import BaseProvider
        return BaseProvider._is_permanent_failure(error)

    def _execute_with_threads_fail_fast(self, tasks: List[Task], options: Dict[str, Any]) -> List[ParallelExecutionResult]:
        return list(self.iter_results(tasks, **options))

    def iter_results(self, tasks, **options):
        """Consume tasks in caller order with at most max_workers retained futures.

        Unlike execute_parallel, this streaming entry point does not sort priorities
        or collect results; the caller controls order and result retention.
        """
        max_workers = max(1, options.get("max_workers", self.max_workers))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        pending = set()
        remaining = iter(tasks)
        stop_dispatch = False

        def submit_next():
            if not stop_dispatch:
                task = next(remaining, None)
                if task is not None:
                    pending.add(executor.submit(_execute_task, task))

        try:
            for _ in range(max_workers):
                submit_next()
            while pending:
                future = next(as_completed(pending))
                pending.remove(future)
                result = future.result()
                del future
                if result.error and (options.get("fail_fast", False) or
                        (options.get("fail_fast_permanent", False) and self._is_permanent_failure(result.error))):
                    stop_dispatch = True
                    for queued in pending:
                        queued.cancel()
                    pending = {f for f in pending if not f.cancelled()}
                yield result
                del result
                submit_next()
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    def _execute_with_processes(self, tasks: List[Task], **options) -> List[ParallelExecutionResult]:
        """Measure execution inside the child, excluding pool queue time."""
        with ProcessPoolExecutor(max_workers=options.get("max_workers", self.max_workers)) as executor:
            futures = [executor.submit(_execute_task, task) for task in tasks]
            return [future.result() for future in as_completed(futures)]

    def execute_pipeline_steps_parallel(
        self, steps: List[PipelineStep], data: Any, **options
    ) -> List[Any]:
        """
        Execute pipeline steps in parallel.

        Args:
            steps: List of steps to execute
            data: Input data
            **options: Additional options

        Returns:
            List of step results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ParallelismManager",
            message=f"Executing {len(steps)} pipeline steps in parallel",
        )

        try:
            # Create tasks from steps
            self.progress_tracker.update_tracking(
                tracking_id, message="Creating tasks from steps..."
            )
            tasks = [
                Task(
                    task_id=step.name,
                    handler=step.handler or (lambda d, **kwargs: d),
                    args=(data,),
                    kwargs=step.config,
                    priority=0,
                )
                for step in steps
            ]

            # Execute tasks
            self.progress_tracker.update_tracking(
                tracking_id, message="Executing tasks in parallel..."
            )
            results = self.execute_parallel(tasks, **options)

            # Map results back to steps
            self.progress_tracker.update_tracking(
                tracking_id, message="Mapping results to steps..."
            )
            result_map = {r.task_id: r for r in results}
            step_results = []

            for step in steps:
                result = result_map.get(step.name)
                if result and result.success:
                    step_results.append(result.result)
                else:
                    raise ProcessingError(
                        f"Step {step.name} failed: {result.error if result else 'Unknown error'}"
                    )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Executed {len(steps)} steps in parallel",
            )
            return step_results

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def identify_parallelizable_steps(
        self, pipeline: Pipeline
    ) -> List[List[PipelineStep]]:
        """
        Identify steps that can be executed in parallel.

        Args:
            pipeline: Pipeline object

        Returns:
            List of step groups that can run in parallel
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ParallelismManager",
            message=f"Identifying parallelizable steps for pipeline: {pipeline.name}",
        )

        try:
            # Group steps by dependency level
            self.progress_tracker.update_tracking(
                tracking_id, message="Analyzing step dependencies..."
            )
            step_map = {step.name: step for step in pipeline.steps}
            dependency_levels = {}

            def get_level(step_name: str) -> int:
                if step_name in dependency_levels:
                    return dependency_levels[step_name]

                step = step_map[step_name]
                if not step.dependencies:
                    level = 0
                else:
                    level = max(get_level(dep) for dep in step.dependencies) + 1

                dependency_levels[step_name] = level
                return level

            # Calculate levels for all steps
            for step in pipeline.steps:
                get_level(step.name)

            # Group by level
            self.progress_tracker.update_tracking(
                tracking_id, message="Grouping steps by dependency level..."
            )
            level_groups = {}
            for step in pipeline.steps:
                level = dependency_levels[step.name]
                if level not in level_groups:
                    level_groups[level] = []
                level_groups[level].append(step)

            # Return groups sorted by level
            result = [level_groups[level] for level in sorted(level_groups.keys())]
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Identified {len(result)} parallelizable step groups",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def optimize_parallel_execution(
        self, pipeline: Pipeline, available_workers: int
    ) -> Dict[str, Any]:
        """
        Optimize parallel execution plan.

        Args:
            pipeline: Pipeline object
            available_workers: Available worker count

        Returns:
            Optimization plan
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="pipeline",
            submodule="ParallelismManager",
            message=f"Optimizing parallel execution for pipeline: {pipeline.name}",
        )

        try:
            self.progress_tracker.update_tracking(
                tracking_id, message="Identifying parallelizable steps..."
            )
            parallel_groups = self.identify_parallelizable_steps(pipeline)

            # Calculate execution plan
            self.progress_tracker.update_tracking(
                tracking_id, message="Calculating execution plan..."
            )
            execution_plan = []
            for group in parallel_groups:
                execution_plan.append(
                    {
                        "steps": [s.name for s in group],
                        "parallel": len(group) > 1,
                        "worker_count": min(len(group), available_workers),
                    }
                )

            result = {
                "execution_plan": execution_plan,
                "total_groups": len(parallel_groups),
                "max_parallelism": max(len(group) for group in parallel_groups)
                if parallel_groups
                else 1,
                "estimated_workers": sum(
                    plan["worker_count"] for plan in execution_plan
                ),
            }

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Optimization complete: {len(parallel_groups)} groups, max parallelism: {result['max_parallelism']}",
            )
            return result

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class ParallelExecutor:
    """Parallel executor for pipeline tasks."""

    def __init__(self, max_workers: int = 4, **config):
        """Initialize parallel executor."""
        self.parallelism_manager = ParallelismManager(max_workers=max_workers, **config)

    def execute_parallel(self, tasks: List[Task]) -> List[ParallelExecutionResult]:
        """Execute tasks in parallel."""
        return self.parallelism_manager.execute_parallel(tasks)
