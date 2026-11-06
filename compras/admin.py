# compras/admin.py

from django.contrib import admin
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from tesoreria.locks import BloqueoTurnoCerradoAdminMixin
from .models import (
    PagoProveedor,
    Proveedor,
    CancelacionDeudaProveedor,
    CancelacionDeudaProveedorDetalle,
    SaldoInicialProveedor,
    CancelacionDeudaProveedorSaldoInicialDetalle,
    AdelantoProveedor,
    CancelacionDeudaProveedorAdelantoDetalle,
)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'total_comprado_display', 'saldo_cc_display', 'estado_cuenta_btn')
    list_filter  = ('activo',)
    search_fields = ('nombre', 'telefono', 'notas')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        qs = qs.annotate(
            _total_comprado=Coalesce(Sum('pagos__importe'), zero),
            _total_cancelado=Coalesce(Sum('pagos__cancelaciones_detalle__monto'), zero),
        )
        return qs

    @admin.display(description=_('Total purchased ($)'), ordering='_total_comprado')
    def total_comprado_display(self, obj):
        val = float(getattr(obj, '_total_comprado', 0))
        return format_html('<span style="font-weight:600">${}</span>', f'{val:,.2f}')

    @admin.display(description=_('Current account balance ($)'), ordering='_total_cancelado')
    def saldo_cc_display(self, obj):
        from django.db.models import Sum
        comprado  = float(getattr(obj, '_total_comprado', 0))
        cancelado = float(getattr(obj, '_total_cancelado', 0))
        inicial = float(
            obj.saldos_iniciales.aggregate(total=Sum('monto')).get('total') or 0
        )
        inicial_cancelado = float(
            CancelacionDeudaProveedorSaldoInicialDetalle.objects
            .filter(saldo_inicial__proveedor=obj)
            .aggregate(total=Sum('monto'))
            .get('total') or 0
        )
        adelantos = float(obj.adelantos.aggregate(total=Sum('monto')).get('total') or 0)
        comprado += inicial
        cancelado += inicial_cancelado
        saldo = comprado - cancelado - adelantos
        color = '#ff5d6c' if saldo > 0 else '#2ecc71'
        return format_html(
            '<span style="font-weight:700;color:{}">${}</span>',
            color, f'{saldo:,.2f}'
        )

    @admin.display(description=_('Account statement'))
    def estado_cuenta_btn(self, obj):
        url = reverse('proveedor_estado_cuenta_pdf', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" '
            'style="background:#1d6f42;color:#fff;padding:3px 10px;border-radius:5px;'
            'font-size:0.8rem;text-decoration:none;white-space:nowrap">PDF CC</a>',
            url
        )


@admin.register(PagoProveedor)
class PagoProveedorAdmin(BloqueoTurnoCerradoAdminMixin, ImportExportModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'proveedor', 'proveedor_ref', 'importe', 'medio_de_pago', 'descripcion')
    list_filter = ('usuario', 'medio_de_pago', 'proveedor_ref')
    date_hierarchy = 'fecha'
    search_fields = ('proveedor', 'proveedor_ref__nombre', 'descripcion', 'usuario__username')


class CancelacionDeudaProveedorDetalleInline(admin.TabularInline):
    model = CancelacionDeudaProveedorDetalle
    extra = 0
    readonly_fields = ('deuda', 'monto')


class CancelacionDeudaProveedorSaldoInicialDetalleInline(admin.TabularInline):
    model = CancelacionDeudaProveedorSaldoInicialDetalle
    extra = 0
    readonly_fields = ('saldo_inicial', 'monto')


class CancelacionDeudaProveedorAdelantoDetalleInline(admin.TabularInline):
    model = CancelacionDeudaProveedorAdelantoDetalle
    extra = 0
    readonly_fields = ('adelanto', 'monto')


@admin.register(CancelacionDeudaProveedor)
class CancelacionDeudaProveedorAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'proveedor', 'total', 'monto_pagado', 'monto_adelanto_aplicado', 'medio_de_pago')
    list_filter = ('usuario', 'medio_de_pago', 'proveedor')
    search_fields = ('proveedor__nombre', 'descripcion', 'usuario__username')
    date_hierarchy = 'fecha'
    inlines = (CancelacionDeudaProveedorDetalleInline, CancelacionDeudaProveedorSaldoInicialDetalleInline, CancelacionDeudaProveedorAdelantoDetalleInline)


class CancelacionDeudaProveedorSaldoInicialDetalleAdminInline(admin.TabularInline):
    model = CancelacionDeudaProveedorSaldoInicialDetalle
    extra = 0
    readonly_fields = ('cancelacion', 'monto')


@admin.register(SaldoInicialProveedor)
class SaldoInicialProveedorAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'proveedor', 'monto', 'saldo_pendiente', 'usuario', 'descripcion')
    list_filter = ('proveedor', 'usuario')
    search_fields = ('proveedor__nombre', 'descripcion')
    date_hierarchy = 'fecha'
    inlines = (CancelacionDeudaProveedorSaldoInicialDetalleAdminInline,)


class CancelacionDeudaProveedorAdelantoDetalleAdminInline(admin.TabularInline):
    model = CancelacionDeudaProveedorAdelantoDetalle
    extra = 0
    readonly_fields = ('cancelacion', 'monto')


@admin.register(AdelantoProveedor)
class AdelantoProveedorAdmin(BloqueoTurnoCerradoAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'fecha', 'proveedor', 'monto', 'monto_aplicado', 'saldo_disponible', 'medio_de_pago', 'usuario', 'descripcion')
    list_filter = ('proveedor', 'usuario', 'medio_de_pago')
    search_fields = ('proveedor__nombre', 'descripcion')
    date_hierarchy = 'fecha'
    inlines = (CancelacionDeudaProveedorAdelantoDetalleAdminInline,)
