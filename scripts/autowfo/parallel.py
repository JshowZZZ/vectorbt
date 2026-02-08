"""Parallel execution helpers for AUTOWFO."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

from scripts.autowfo import evaluator as autowfo_evaluator


_WORKER_RUNTIME = None


def _init_combo_worker(runtime):
    global _WORKER_RUNTIME
    _WORKER_RUNTIME = runtime


def _evaluate_combo_task_in_worker(task):
    if _WORKER_RUNTIME is None:
        raise RuntimeError("worker runtime is not initialized")
    return autowfo_evaluator.evaluate_combo_task(task, _WORKER_RUNTIME)


def _run_combo_tasks(tasks, runtime, max_workers):
    if max_workers <= 1:
        for task in tasks:
            yield autowfo_evaluator.evaluate_combo_task(task, runtime)
        return

    task_count = len(tasks) if hasattr(tasks, "__len__") else None
    chunksize = 1
    if task_count and task_count > 0:
        chunksize = max(1, task_count // (max_workers * 8))

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_combo_worker,
        initargs=(runtime,),
    ) as executor:
        # executor.map preserves input order, so downstream rows stay deterministic.
        for result in executor.map(_evaluate_combo_task_in_worker, tasks, chunksize=chunksize):
            yield result
