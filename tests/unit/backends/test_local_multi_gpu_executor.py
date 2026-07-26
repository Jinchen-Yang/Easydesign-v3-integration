from __future__ import annotations

import threading
import time

from easydesign.backends.executors import execute_on_devices


def test_executor_runs_one_serial_bucket_per_device_and_preserves_input_order() -> None:
    lock = threading.Lock()
    active: dict[int, int] = {0: 0, 1: 0}
    maximum: dict[int, int] = {0: 0, 1: 0}

    def worker(value: int, device: int) -> str:
        with lock:
            active[device] += 1
            maximum[device] = max(maximum[device], active[device])
        time.sleep(0.01)
        with lock:
            active[device] -= 1
        return f"{device}:{value}"

    results = execute_on_devices(
        (10, 11, 12, 13, 14),
        devices=(0, 1),
        worker=worker,
    )

    assert tuple(item.input_index for item in results) == (0, 1, 2, 3, 4)
    assert tuple(item.device for item in results) == (0, 1, 0, 1, 0)
    assert maximum == {0: 1, 1: 1}


def test_executor_drain_stops_after_current_items() -> None:
    completed: list[int] = []
    drain = False

    def worker(value: int, _device: int) -> int:
        nonlocal drain
        completed.append(value)
        drain = True
        return value

    results = execute_on_devices(
        (10, 11, 12, 13),
        devices=(0,),
        worker=worker,
        should_stop=lambda: drain,
    )

    assert completed == [10]
    assert tuple(item.result for item in results) == (10,)
