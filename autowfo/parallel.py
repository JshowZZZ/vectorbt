"""Parallel execution helpers for AUTOWFO."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

from autowfo import evaluator as autowfo_evaluator


_WORKER_RUNTIME = None


def _init_combo_worker(runtime):
    global _WORKER_RUNTIME
    _WORKER_RUNTIME = runtime


def _evaluate_combo_task_in_worker(task):
    if _WORKER_RUNTIME is None:
        raise RuntimeError("worker runtime is not initialized")
    return autowfo_evaluator.evaluate_combo_task(task, _WORKER_RUNTIME)


def _evaluate_combo_chunk_in_worker(task_chunk):
    if _WORKER_RUNTIME is None:
        raise RuntimeError("worker runtime is not initialized")
    return [
        autowfo_evaluator.evaluate_combo_task(task, _WORKER_RUNTIME)
        for task in task_chunk
    ]


def _chunk_tasks(tasks, chunk_size):
    for start in range(0, len(tasks), chunk_size):
        yield tasks[start:start + chunk_size]


def _run_combo_tasks(tasks, runtime, max_workers):
    task_list = list(tasks)
    if not task_list:
        return

    if max_workers <= 1:
        for task in task_list:
            yield autowfo_evaluator.evaluate_combo_task(task, runtime)
        return

    task_count = len(task_list)
    chunk_size = max(1, task_count // (max_workers * 4))
    task_chunks = list(_chunk_tasks(task_list, chunk_size))

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_combo_worker,
        initargs=(runtime,),
    ) as executor:
        # executor.map preserves input order, so downstream rows stay deterministic.
        for chunk_results in executor.map(
            _evaluate_combo_chunk_in_worker,
            task_chunks,
            chunksize=1,
        ):
            for result in chunk_results:
                yield result

