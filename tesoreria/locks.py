# tesoreria/locks.py
"""
Candado de turno cerrado.

Un turno de caja cerrado es INMUTABLE: ni el turno ni las operaciones que le
pertenecen (ventas, gastos, cobros, retiros, etc.) pueden crearse, editarse ni
borrarse. Las correcciones posteriores se registran con ``AjusteCuenta``
(documento explícito con usuario, fecha y motivo).

El candado tiene dos capas:

1. Backstop a nivel de modelo (este módulo): receivers ``pre_save`` /
   ``pre_delete`` que levantan ``PermissionDenied``. Cubre admin, shell,
   scripts y cualquier código que intente tocar datos de un turno cerrado.
2. UX en el admin: ``BloqueoTurnoCerradoAdminMixin`` deshabilita la edición y
   el borrado de esos objetos (quedan en modo solo-lectura).

Excepción documentada: la anulación de un ``AdelantoCliente`` (transición de
``estado`` con evento de auditoría propio) se permite aunque el turno esté
cerrado, siempre que el save use ``update_fields`` restringido a los campos de
anulación.
"""

from django.core.exceptions import PermissionDenied
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext, gettext_noop

from core.sync_estado import pausa_en_sync


# Campos que puede tocar la anulación auditada de un adelanto de cliente.
_CAMPOS_ANULACION_ADELANTO = {'estado', 'anulado_en', 'anulado_por', 'motivo_anulacion'}

# Modelo → ruta de atributos hasta el TurnoCaja dueño de la operación.
_RUTAS_TURNO = {
    'ventas.Venta': 'turno',
    'ventas.VentaPago': 'venta.turno',
    'ventas.VentaCategoriaDetalle': 'venta.turno',
    'ventas.VentaItem': 'venta.turno',
    'ventas.RetiroEfectivo': 'turno',
    'ventas.CobroDeuda': 'turno',
    'ventas.CobroDeudaDetalle': 'cobro.turno',
    'ventas.CobroDeudaSaldoInicialDetalle': 'cobro.turno',
    'ventas.CobroDeudaAdelantoDetalle': 'cobro.turno',
    'ventas.AdelantoCliente': 'turno',
    'gastos.Gasto': 'turno',
    'compras.PagoProveedor': 'turno',
    'compras.CancelacionDeudaProveedor': 'turno',
    'compras.CancelacionDeudaProveedorDetalle': 'cancelacion.turno',
    'compras.CancelacionDeudaProveedorSaldoInicialDetalle': 'cancelacion.turno',
    'compras.CancelacionDeudaProveedorAdelantoDetalle': 'cancelacion.turno',
    'compras.AdelantoProveedor': 'turno',
}


def turno_cerrado(turno):
    return turno is not None and not turno.abierto and turno.cerrado_en is not None


def resolver_turno(obj):
    """Devuelve el TurnoCaja dueño de ``obj`` (o el propio obj si es un turno)."""
    if obj is None:
        return None
    label = f'{obj._meta.app_label}.{obj.__class__.__name__}'
    if label == 'ventas.TurnoCaja':
        return obj
    ruta = _RUTAS_TURNO.get(label)
    if not ruta:
        return None
    actual = obj
    for attr in ruta.split('.'):
        actual = getattr(actual, attr, None)
        if actual is None:
            return None
    return actual


_ACCIONES = {
    'crear ni modificar': gettext_noop('crear ni modificar'),
    'modificar': gettext_noop('modificar'),
    'eliminar': gettext_noop('eliminar'),
}


def _denegar(accion, instance, turno):
    raise PermissionDenied(
        gettext('No se puede %(accion)s "%(objeto)s" del turno #%(turno)s: '
                'el turno está cerrado y es inmutable. Registrá la corrección con un '
                'Ajuste de cuenta (Tesorería) indicando el motivo.') % {
            'accion': gettext(_ACCIONES.get(accion, accion)),
            'objeto': instance._meta.verbose_name,
            'turno': turno.pk,
        }
    )


def _es_anulacion_adelanto(sender, update_fields):
    if f'{sender._meta.app_label}.{sender.__name__}' != 'ventas.AdelantoCliente':
        return False
    if not update_fields:
        return False
    return set(update_fields) <= _CAMPOS_ANULACION_ADELANTO


# ---------------------------------------------------------------------------
# TurnoCaja: una vez cerrado, inmutable e imborrable
# ---------------------------------------------------------------------------

@receiver(pre_save, sender='ventas.TurnoCaja')
@pausa_en_sync
def _bloquear_save_turno_cerrado(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previo = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if turno_cerrado(previo):
        raise PermissionDenied(
            gettext('El turno #%(turno)s está cerrado y no puede modificarse. '
                    'Las correcciones se registran con Ajustes de cuenta.') % {'turno': instance.pk}
        )


@receiver(pre_delete, sender='ventas.TurnoCaja')
@pausa_en_sync
def _bloquear_delete_turno_cerrado(sender, instance, **kwargs):
    if turno_cerrado(instance):
        raise PermissionDenied(
            gettext('El turno #%(turno)s está cerrado y no puede eliminarse.') % {'turno': instance.pk}
        )


# ---------------------------------------------------------------------------
# Operaciones: bloqueadas si su turno está cerrado
# ---------------------------------------------------------------------------

@pausa_en_sync
def _guard_save_operacion(sender, instance, **kwargs):
    if _es_anulacion_adelanto(sender, kwargs.get('update_fields')):
        return
    # Estado nuevo: no se puede crear/mover una operación hacia un turno cerrado.
    turno = resolver_turno(instance)
    if turno_cerrado(turno):
        _denegar('crear ni modificar', instance, turno)
    # Estado previo: no se puede editar una operación que ya pertenece a un turno cerrado.
    if instance.pk:
        try:
            previo = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            return
        turno_previo = resolver_turno(previo)
        if turno_cerrado(turno_previo):
            _denegar('modificar', instance, turno_previo)


@pausa_en_sync
def _guard_delete_operacion(sender, instance, **kwargs):
    turno = resolver_turno(instance)
    if turno_cerrado(turno):
        _denegar('eliminar', instance, turno)


for _label in _RUTAS_TURNO:
    pre_save.connect(_guard_save_operacion, sender=_label, weak=False,
                     dispatch_uid=f'lock_save_{_label}')
    pre_delete.connect(_guard_delete_operacion, sender=_label, weak=False,
                       dispatch_uid=f'lock_delete_{_label}')


# ---------------------------------------------------------------------------
# Mixin de admin: modo solo-lectura para objetos de turnos cerrados
# ---------------------------------------------------------------------------

class BloqueoTurnoCerradoAdminMixin:
    """Deshabilita cambiar/borrar en el admin los objetos de un turno cerrado."""

    def _turno_bloqueado(self, obj):
        return turno_cerrado(resolver_turno(obj))

    def has_change_permission(self, request, obj=None):
        if obj is not None and self._turno_bloqueado(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self._turno_bloqueado(obj):
            return False
        return super().has_delete_permission(request, obj)
