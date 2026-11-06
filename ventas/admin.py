# ventas/admin.py

from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from tesoreria.locks import BloqueoTurnoCerradoAdminMixin, turno_cerrado
from .models import (
    TurnoCaja,
    Venta,
    VentaCategoriaDetalle,
    VentaItem,
    Comanda,
    ComandaItem,
    RetiroEfectivo,
    Cliente,
    CobroDeuda,
    CobroDeudaDetalle,
    SaldoInicialCliente,
    CobroDeudaSaldoInicialDetalle,
    AdelantoCliente,
    AdelantoClienteAnulacionEvento,
    CobroDeudaAdelantoDetalle,
)


def _snapshot_cobro_destinos(cobro):
    destinos = []
    for detalle in cobro.detalles.all():
        destinos.append({
            'tipo': 'venta',
            'referencia': f'Ticket #{detalle.venta.numero_ticket}',
            'monto': float(detalle.monto),
        })
    for detalle in cobro.detalles_saldo_inicial.all():
        destinos.append({
            'tipo': 'saldo_inicial',
            'referencia': detalle.saldo_inicial.descripcion or 'Saldo inicial',
            'monto': float(detalle.monto),
        })
    return destinos


def _revertir_y_anular_adelantos(queryset, usuario, motivo='Anulado desde administracion'):
    adelantos = list(queryset.select_related('cliente'))
    if not adelantos:
        return {
            'anulados': 0,
            'cobros_revertidos': 0,
            'ya_anulados': 0,
            'bloqueados': 0,
            'errores': [],
        }

    activos = [a for a in adelantos if a.estado == AdelantoCliente.ESTADO_ACTIVO]
    activos_ids = {a.pk for a in activos}
    ya_anulados = len(adelantos) - len(activos)

    detalles = list(
        CobroDeudaAdelantoDetalle.objects.filter(adelanto_id__in=activos_ids)
        .select_related('adelanto', 'cobro')
        .prefetch_related(
            'cobro__detalles__venta',
            'cobro__detalles_saldo_inicial__saldo_inicial',
            'cobro__detalles_adelanto__adelanto',
        )
    )

    cobros_por_id = {}
    for detalle in detalles:
        cobros_por_id[detalle.cobro_id] = detalle.cobro

    cobros_bloqueados = {}
    for cobro_id, cobro in cobros_por_id.items():
        if turno_cerrado(cobro.turno):
            cobros_bloqueados[cobro_id] = (
                f'Cobro #{cobro_id} bloqueado: pertenece al turno cerrado #{cobro.turno_id} '
                '(inmutable — corregí con un Ajuste de cuenta).'
            )
            continue
        adelantos_en_cobro = {d.adelanto_id for d in cobro.detalles_adelanto.all()}
        externos = sorted(adelantos_en_cobro - activos_ids)
        if externos:
            cobros_bloqueados[cobro_id] = (
                f'Cobro #{cobro_id} bloqueado: usa adelantos fuera de la seleccion ({", ".join(str(x) for x in externos)}).'
            )
            continue
        monto_recibido = cobro.monto_recibido or Decimal('0')
        if monto_recibido > 0:
            cobros_bloqueados[cobro_id] = (
                f'Cobro #{cobro_id} bloqueado: tiene monto recibido (${monto_recibido:,.2f}).'
            )

    adelantos_bloqueados_ids = {
        detalle.adelanto_id
        for detalle in detalles
        if detalle.cobro_id in cobros_bloqueados
    }

    validos = [a for a in activos if a.pk not in adelantos_bloqueados_ids]
    validos_ids = {a.pk for a in validos}
    detalles_validos = [
        d for d in detalles
        if d.adelanto_id in validos_ids and d.cobro_id not in cobros_bloqueados
    ]

    cobros_a_revertir = {}
    eventos_por_adelanto = {a.pk: [] for a in validos}
    for detalle in detalles_validos:
        cobro = detalle.cobro
        cobros_a_revertir[cobro.pk] = cobro
        eventos_por_adelanto[detalle.adelanto_id].append({
            'cobro_id': cobro.pk,
            'fecha': timezone.localtime(cobro.fecha).isoformat(),
            'monto_adelanto': float(detalle.monto),
            'cobro_total': float(cobro.total or 0),
            'destinos': _snapshot_cobro_destinos(cobro),
        })

    now = timezone.now()
    with transaction.atomic():
        for adelanto in validos:
            detalle_evento = eventos_por_adelanto.get(adelanto.pk, [])
            monto_revertido = sum(
                Decimal(str(item.get('monto_adelanto', 0))) for item in detalle_evento
            )
            AdelantoClienteAnulacionEvento.objects.create(
                adelanto=adelanto,
                fecha=now,
                usuario=usuario,
                motivo=motivo,
                monto_revertido=monto_revertido,
                detalle=detalle_evento,
            )
            adelanto.estado = AdelantoCliente.ESTADO_ANULADO
            adelanto.anulado_en = now
            adelanto.anulado_por = usuario
            adelanto.motivo_anulacion = motivo
            adelanto.save(update_fields=['estado', 'anulado_en', 'anulado_por', 'motivo_anulacion'])

        if cobros_a_revertir:
            CobroDeuda.objects.filter(pk__in=cobros_a_revertir.keys()).delete()

    return {
        'anulados': len(validos),
        'cobros_revertidos': len(cobros_a_revertir),
        'ya_anulados': ya_anulados,
        'bloqueados': len(adelantos_bloqueados_ids),
        'errores': sorted(set(cobros_bloqueados.values())),
    }


@admin.action(description=_('Revert and void selected customer advances'))
def revertir_y_anular_adelantos_action(modeladmin, request, queryset):
    resultado = _revertir_y_anular_adelantos(queryset, request.user)

    if resultado['anulados']:
        modeladmin.message_user(
            request,
            _(
                'Advances voided: %(adelantos)s | debt collections reverted: %(cobros)s'
            ) % {
                'adelantos': resultado['anulados'],
                'cobros': resultado['cobros_revertidos'],
            },
            level=messages.SUCCESS,
        )
    if resultado['ya_anulados']:
        modeladmin.message_user(
            request,
            _('Already voided (ignored): %(cantidad)s') % {'cantidad': resultado['ya_anulados']},
            level=messages.INFO,
        )
    if resultado['bloqueados']:
        modeladmin.message_user(
            request,
            _('Blocked by guardrails: %(cantidad)s') % {'cantidad': resultado['bloqueados']},
            level=messages.WARNING,
        )
    for error in resultado['errores'][:8]:
        modeladmin.message_user(request, error, level=messages.WARNING)


class VentaItemInline(admin.TabularInline):
    model = VentaItem
    extra = 0


class VentaCategoriaDetalleInline(admin.TabularInline):
    model = VentaCategoriaDetalle
    extra = 0


@admin.action(description=_('Download closing PDF (one shift only)'))
def descargar_cierre_pdf_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(
            request,
            _('Select exactly one shift to download the PDF.'),
            level=messages.WARNING,
        )
        return None
    turno = queryset.first()
    url = reverse('pos:api_turno_pdf', args=[turno.pk])
    return HttpResponseRedirect(url)


@admin.register(TurnoCaja)
class TurnoCajaAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = (
        'id', 'fecha', 'usuario', 'abierto',
        'saldo_inicial', 'cuenta_origen', 'saldo_final', 'diferencia_cierre_coloreada', 'cerrado_en',
        'descargar_cierre_pdf',
    )
    list_filter = ('abierto', 'cuenta_origen')
    date_hierarchy = 'fecha'
    readonly_fields = ('cerrado_en', 'diferencia_cierre', 'motivo_diferencia', 'abierto_en')
    actions = (descargar_cierre_pdf_action,)

    @admin.display(description=_('Diferencia cierre'))
    def diferencia_cierre_coloreada(self, obj):
        if obj.diferencia_cierre is None:
            return '—'
        d = obj.diferencia_cierre
        color = 'green' if d > 0 else ('red' if d < 0 else 'gray')
        label = 'sobrante' if d > 0 else ('faltante' if d < 0 else 'exacto')
        return format_html(
            '<span style="color:{};font-weight:bold;">{}{} ({})</span>',
            color,
            '+' if d > 0 else '',
            f'{d:,.2f}',
            label,
        )

    @admin.display(description=_('Closing PDF'))
    def descargar_cierre_pdf(self, obj):
        url = reverse('pos:api_turno_pdf', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">{}</a>', url, _('Download'))


@admin.register(Venta)
class VentaAdmin(BloqueoTurnoCerradoAdminMixin, ImportExportModelAdmin):
    list_display = ('id', 'numero_ticket', 'fecha', 'usuario', 'cliente', 'categoria', 'importe', 'medio_de_pago', 'descripcion')
    list_filter = ('usuario', 'categoria', 'medio_de_pago', 'cliente')
    date_hierarchy = 'fecha'
    search_fields = ('descripcion', 'cliente__nombre', 'usuario__username')
    inlines = (VentaItemInline, VentaCategoriaDetalleInline)


class ComandaItemInline(admin.TabularInline):
    model = ComandaItem
    extra = 0


@admin.register(Comanda)
class ComandaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'fecha', 'creada_en', 'carnicero', 'puesto', 'estado', 'total', 'venta')
    list_filter = ('estado', 'carnicero', 'puesto')
    date_hierarchy = 'fecha'
    inlines = (ComandaItemInline,)


@admin.register(RetiroEfectivo)
class RetiroEfectivoAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'fecha', 'importe', 'descripcion', 'usuario')
    list_filter = ('usuario',)
    date_hierarchy = 'fecha'


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'total_comprado_display', 'saldo_cc_display', 'estado_cuenta_btn')
    list_filter  = ('activo',)
    search_fields = ('nombre', 'telefono')

    def get_queryset(self, request):
        from django.db.models import Sum, Value, DecimalField, Q
        from django.db.models.functions import Coalesce
        qs = super().get_queryset(request)
        zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        qs = qs.annotate(
            _total_ventas=Coalesce(Sum('ventas__importe'), zero),
            _total_cc=Coalesce(
                Sum('ventas__importe',
                    filter=Q(ventas__medio_de_pago__categoria='Cuenta Corriente')),
                zero,
            ),
            _total_cobrado=Coalesce(Sum('ventas__cobros_detalle__monto'), zero),
        )
        return qs

    @admin.display(description=_('Total purchased ($)'), ordering='_total_ventas')
    def total_comprado_display(self, obj):
        val = float(getattr(obj, '_total_ventas', 0))
        return format_html('<span style="font-weight:600">${}</span>', f'{val:,.2f}')

    @admin.display(description=_('Current account balance ($)'), ordering='_total_cc')
    def saldo_cc_display(self, obj):
        from django.db.models import Sum
        cc = float(sum(v.monto_fiado for v in obj.ventas.prefetch_related('pagos__medio_de_pago').all()))
        inicial = float(
            obj.saldos_iniciales.aggregate(total=Sum('monto')).get('total') or 0
        )
        cobrado_directo = float(
            obj.cobros.aggregate(total=Sum('monto_recibido')).get('total') or 0
        )
        adelantos = float(
            obj.adelantos.filter(estado=AdelantoCliente.ESTADO_ACTIVO).aggregate(total=Sum('monto')).get('total') or 0
        )
        cc += inicial
        saldo = cc - cobrado_directo - adelantos
        color = '#ff5d6c' if saldo > 0 else '#2ecc71'
        return format_html(
            '<span style="font-weight:700;color:{}">${}</span>',
            color, f'{saldo:,.2f}'
        )

    @admin.display(description=_('Account statement'))
    def estado_cuenta_btn(self, obj):
        from django.urls import reverse
        url = reverse('cliente_estado_cuenta_pdf', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" '
            'style="background:#1d6f42;color:#fff;padding:3px 10px;border-radius:5px;'
            'font-size:0.8rem;text-decoration:none;white-space:nowrap">PDF CC</a>',
            url
        )


class CobroDeudaDetalleInline(admin.TabularInline):
    model = CobroDeudaDetalle
    extra = 0
    readonly_fields = ('venta', 'monto')


class CobroDeudaSaldoInicialDetalleInline(admin.TabularInline):
    model = CobroDeudaSaldoInicialDetalle
    extra = 0
    readonly_fields = ('saldo_inicial', 'monto')


class CobroDeudaAdelantoDetalleInline(admin.TabularInline):
    model = CobroDeudaAdelantoDetalle
    extra = 0
    readonly_fields = ('adelanto', 'monto')


@admin.register(CobroDeuda)
class CobroDeudaAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'fecha', 'cliente', 'total', 'monto_recibido', 'monto_adelanto_aplicado', 'medio_de_pago', 'usuario')
    list_filter = ('usuario', 'medio_de_pago', 'cliente')
    search_fields = ('cliente__nombre', 'descripcion')
    date_hierarchy = 'fecha'
    inlines = (CobroDeudaDetalleInline, CobroDeudaSaldoInicialDetalleInline, CobroDeudaAdelantoDetalleInline)


class CobroDeudaSaldoInicialDetalleAdminInline(admin.TabularInline):
    model = CobroDeudaSaldoInicialDetalle
    extra = 0
    readonly_fields = ('cobro', 'monto')


@admin.register(SaldoInicialCliente)
class SaldoInicialClienteAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'cliente', 'monto', 'saldo_pendiente', 'usuario', 'descripcion')
    list_filter = ('cliente', 'usuario')
    search_fields = ('cliente__nombre', 'descripcion')
    date_hierarchy = 'fecha'
    inlines = (CobroDeudaSaldoInicialDetalleAdminInline,)


class CobroDeudaAdelantoDetalleAdminInline(admin.TabularInline):
    model = CobroDeudaAdelantoDetalle
    extra = 0
    readonly_fields = ('cobro', 'monto')


class AdelantoClienteAnulacionEventoInline(admin.TabularInline):
    model = AdelantoClienteAnulacionEvento
    extra = 0
    can_delete = False
    readonly_fields = ('fecha', 'usuario', 'motivo', 'monto_revertido', 'detalle')


@admin.register(AdelantoCliente)
class AdelantoClienteAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = (
        'id', 'fecha', 'cliente', 'monto', 'monto_aplicado', 'saldo_disponible',
        'estado', 'anulado_en', 'anulado_por', 'medio_de_pago', 'usuario', 'descripcion'
    )
    list_filter = ('estado', 'cliente', 'usuario', 'medio_de_pago')
    search_fields = ('cliente__nombre', 'descripcion')
    date_hierarchy = 'fecha'
    readonly_fields = ('estado', 'anulado_en', 'anulado_por', 'motivo_anulacion')
    actions = (revertir_y_anular_adelantos_action,)
    inlines = (CobroDeudaAdelantoDetalleAdminInline, AdelantoClienteAnulacionEventoInline)
