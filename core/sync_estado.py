# core/sync_estado.py
"""
Interruptor "estoy aplicando datos sincronizados".

Mientras se aplican registros que llegan de otra base (la sucursal subiendo a
la central, o la central bajando a la sucursal), las señales que generan
movimientos automáticos, bloquean turnos cerrados o anotan cambios para
sincronizar no deben correr: los registros derivados ya vienen en el lote, y
volver a generarlos los duplicaría.
"""

import functools
import threading
from contextlib import contextmanager

_estado = threading.local()


def sincronizando():
    return getattr(_estado, 'activo', False)


@contextmanager
def aplicando_sync():
    previo = sincronizando()
    _estado.activo = True
    try:
        yield
    finally:
        _estado.activo = previo


def pausa_en_sync(receptor):
    """Decorador para receptores de señales que no deben correr al aplicar un lote."""
    @functools.wraps(receptor)
    def envoltura(*args, **kwargs):
        if sincronizando():
            return None
        return receptor(*args, **kwargs)
    return envoltura
