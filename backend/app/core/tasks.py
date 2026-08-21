"""Utilidad para tareas en segundo plano rastreadas (N3).

`asyncio.create_task` sin retener la referencia permite que el GC recolecte la tarea
a mitad de ejecución (footgun documentado de asyncio). `spawn()` guarda la referencia
en un set a nivel de módulo y la descarta al completarse.
"""
from __future__ import annotations

import asyncio
from typing import Coroutine

_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine) -> asyncio.Task:
    """Programa una corrutina en background reteniendo su referencia hasta que termine."""
    task = asyncio.get_running_loop().create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
