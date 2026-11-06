# core/agente_sync.py
"""
Agente de sincronización de la sucursal: sube su cola de cambios a la central
y baja catálogo, precios, plantillas y despachos.

Se corre con ``python manage.py sincronizar`` (una vez o en bucle). Si no hay
internet no pasa nada: la cola espera y la sucursal sigue vendiendo.
"""

from collections import defaultdict

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import CambioSync, Configuracion, Sucursal
from .sincronizacion import (
    SyncError, aplicar_lote, armar_lote, etiqueta, modelos_centrales, modelos_de_sucursal, serializar,
)
from .sync import get_sucursal_actual

LOTE_SUBIDA = 400
TIMEOUT = 30


class ClienteCentral:
    def __init__(self, url=None, token=None):
        self.url = (url or settings.SYNC_URL).rstrip('/')
        self.token = token or settings.SYNC_TOKEN
        if not self.url or not self.token:
            raise SyncError('Falta configurar SYNC_URL y SYNC_TOKEN en el .env de la sucursal.')
        self.http = requests.Session()
        self.http.headers['Authorization'] = f'Bearer {self.token}'

    def _respuesta(self, r):
        try:
            datos = r.json()
        except ValueError:
            raise SyncError(f'La central respondió {r.status_code} sin JSON.')
        if not datos.get('ok'):
            raise SyncError(datos.get('error') or f'La central respondió {r.status_code}.')
        return datos

    def get(self, ruta, **params):
        try:
            return self._respuesta(self.http.get(f'{self.url}{ruta}', params=params, timeout=TIMEOUT))
        except requests.RequestException as exc:
            raise SyncError(f'Sin conexión con la central: {exc.__class__.__name__}')

    def post(self, ruta, cuerpo):
        try:
            return self._respuesta(self.http.post(f'{self.url}{ruta}', json=cuerpo, timeout=TIMEOUT))
        except requests.RequestException as exc:
            raise SyncError(f'Sin conexión con la central: {exc.__class__.__name__}')


def orden_por_dependencias(modelos):
    """Padres antes que hijos; los modelos con referencias genéricas (movimientos) al final."""
    from .sincronizacion import _gfks

    conjunto = set(modelos)
    deps = defaultdict(set)
    for m in modelos:
        for f in m._meta.concrete_fields:
            if f.is_relation and f.related_model in conjunto and f.related_model is not m:
                deps[m].add(f.related_model)
    resultado, visitados = [], set()

    def visitar(m, camino=()):
        if m in visitados or m in camino:
            return
        for d in deps[m]:
            visitar(d, camino + (m,))
        visitados.add(m)
        resultado.append(m)

    for m in sorted(modelos, key=lambda x: (bool(_gfks(x)), etiqueta(x))):
        visitar(m)
    return sorted(resultado, key=lambda m: bool(_gfks(m)))


def adoptar_identidad(cliente):
    """La sucursal local toma el uuid, código y nombre que le asignó la central."""
    remota = cliente.get('/sync/estado/')['sucursal']
    local = Sucursal.objects.get(pk=get_sucursal_actual())
    cambios = {k: remota[k] for k in ('codigo', 'nombre', 'supermercado', 'direccion') if getattr(local, k) != remota[k]}
    if str(local.uuid) != remota['uuid']:
        cambios['uuid'] = remota['uuid']
    if cambios:
        Sucursal.objects.filter(pk=local.pk).update(**cambios)
    return remota


def subir(cliente):
    total = 0
    while True:
        filas = list(CambioSync.objects.order_by('id')[:LOTE_SUBIDA])
        if not filas:
            return total
        cambios = armar_lote(filas)
        if cambios:
            total += cliente.post('/sync/subir/', {'cambios': cambios})['aplicados']
        CambioSync.objects.filter(id__lte=filas[-1].id).delete()


def subir_catalogo(cliente):
    """Primera vez: manda el catálogo local (la central solo crea lo que no tenga)."""
    total = 0
    for model in orden_por_dependencias(modelos_centrales()):
        objetos = list(model.objects.all())
        for i in range(0, len(objetos), LOTE_SUBIDA):
            lote = [{'modelo': etiqueta(model), 'uuid': str(o.uuid), 'op': CambioSync.OP_GUARDAR, 'datos': serializar(o)}
                    for o in objetos[i:i + LOTE_SUBIDA]]
            total += cliente.post('/sync/subir/', {'cambios': lote})['aplicados']
    return total


def bajar(cliente):
    cfg = Configuracion.objects.first() or Configuracion.objects.create()
    total = 0
    while True:
        datos = cliente.get('/sync/bajar/', desde=cfg.sync_cursor_bajada)
        with transaction.atomic():
            if datos['cambios']:
                total += aplicar_lote(datos['cambios'], permitidos=modelos_centrales())
            cfg.sync_cursor_bajada = datos['cursor']
            cfg.save(update_fields=['sync_cursor_bajada'])
        if not datos.get('hay_mas'):
            return total


def encolar_datos_existentes():
    """Para la primera sincronización de una sucursal que ya tenía datos."""
    from .sincronizacion import encolar_todo

    return encolar_todo(orden_por_dependencias(modelos_de_sucursal()))


def sincronizar(cliente=None, catalogo=False):
    cliente = cliente or ClienteCentral()
    cfg = Configuracion.objects.first() or Configuracion.objects.create()
    try:
        adoptar_identidad(cliente)
        resultado = {'catalogo': subir_catalogo(cliente) if catalogo else 0}
        resultado['subidos'] = subir(cliente)
        resultado['bajados'] = bajar(cliente)
    except SyncError as exc:
        Configuracion.objects.filter(pk=cfg.pk).update(sync_ultimo_error=str(exc)[:500])
        raise
    Configuracion.objects.filter(pk=cfg.pk).update(sync_ultima=timezone.now(), sync_ultimo_error='')
    return resultado
