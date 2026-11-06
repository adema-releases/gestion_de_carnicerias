# tesoreria/admin.py

from decimal import Decimal

from django import forms
from django.contrib import admin
from django.db.models import Case, DecimalField, F, Sum, When
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin

from .models import AjusteCuenta, AsignacionMedioPagoCajero, MedioDePago, MovimientoCuenta, TransferenciaCuenta


# ---------------------------------------------------------------------------
# Inline: últimos 30 movimientos de una cuenta
# ---------------------------------------------------------------------------

class MovimientoCuentaInline(admin.TabularInline):
    model = MovimientoCuenta
    fk_name = 'medio_de_pago'
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    fields = ('fecha', 'tipo', 'signo', 'monto', 'usuario', 'turno', 'descripcion')
    readonly_fields = ('fecha', 'tipo', 'signo', 'monto', 'usuario', 'turno', 'descripcion')
    verbose_name = _("Movimiento (últimos 30)")
    verbose_name_plural = _("Últimos 30 movimientos — ver todos en Movimientos de cuenta")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('usuario', 'turno')
            .order_by('-fecha', '-id')
        )

    def get_formset(self, request, obj=None, **kwargs):
        FormSet = super().get_formset(request, obj, **kwargs)
        if obj is None:
            return FormSet

        ids = list(
            MovimientoCuenta.objects.filter(medio_de_pago=obj)
            .order_by('-fecha', '-id')
            .values_list('id', flat=True)[:30]
        )

        class Limited(FormSet):
            def get_queryset(self):
                return (
                    MovimientoCuenta.objects
                    .filter(pk__in=ids)
                    .select_related('usuario', 'turno')
                    .order_by('-fecha', '-id')
                )

        return Limited


# ---------------------------------------------------------------------------
# MedioDePago admin
# ---------------------------------------------------------------------------

@admin.register(MedioDePago)
class MedioDePagoAdmin(ImportExportModelAdmin):
    list_display = ('nombre', 'categoria', 'saldo_actual')
    list_filter = ('categoria',)
    search_fields = ('nombre',)
    readonly_fields = ('saldo_actual',)
    inlines = [MovimientoCuentaInline]

    def saldo_actual(self, obj):
        result = obj.movimientos.aggregate(
            saldo=Sum(
                Case(
                    When(signo=MovimientoCuenta.SIGNO_INGRESO, then=F('monto')),
                    When(signo=MovimientoCuenta.SIGNO_EGRESO, then=-F('monto')),
                    output_field=DecimalField(),
                )
            )
        )
        saldo = result['saldo'] or Decimal('0.00')
        color = 'green' if saldo >= 0 else 'red'
        return format_html(
            '<span style="color:{};font-weight:bold;">${}</span>',
            color,
            f'{saldo:,.2f}',
        )

    saldo_actual.short_description = _('Saldo actual')


# ---------------------------------------------------------------------------
# AsignacionMedioPagoCajero admin
# ---------------------------------------------------------------------------

@admin.register(AsignacionMedioPagoCajero)
class AsignacionMedioPagoCajeroAdmin(admin.ModelAdmin):
    list_display = ('user', 'medio_de_pago', 'activo', 'creado_en')
    list_filter = ('activo', 'medio_de_pago')
    search_fields = ('user__username', 'medio_de_pago__nombre')
    autocomplete_fields = ('user', 'medio_de_pago')
    list_editable = ('activo',)


# ---------------------------------------------------------------------------
# AjusteCuenta admin
# ---------------------------------------------------------------------------

@admin.register(AjusteCuenta)
class AjusteCuentaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'medio_de_pago', 'monto_coloreado', 'usuario', 'descripcion_corta')
    list_filter = ('medio_de_pago',)
    search_fields = ('descripcion', 'usuario__username', 'medio_de_pago__nombre')
    date_hierarchy = 'fecha'
    autocomplete_fields = ('medio_de_pago',)
    readonly_fields = ('usuario', 'creado_en')
    fields = ('medio_de_pago', 'fecha', 'monto', 'descripcion', 'usuario', 'creado_en')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)

    def monto_coloreado(self, obj):
        color = 'green' if obj.monto >= 0 else 'red'
        sign = '+' if obj.monto >= 0 else ''
        return format_html(
            '<span style="color:{};font-weight:bold;">{}{}</span>',
            color, sign, f'{obj.monto:,.2f}',
        )
    monto_coloreado.short_description = _('Monto')
    monto_coloreado.admin_order_field = 'monto'

    def descripcion_corta(self, obj):
        return obj.descripcion[:60] + '…' if len(obj.descripcion) > 60 else obj.descripcion
    descripcion_corta.short_description = _('Descripción')


# ---------------------------------------------------------------------------
# TransferenciaCuenta admin
# ---------------------------------------------------------------------------

@admin.register(TransferenciaCuenta)
class TransferenciaCuentaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'cuenta_origen', 'cuenta_destino', 'monto_coloreado', 'usuario', 'descripcion_corta')
    list_filter = ('cuenta_origen', 'cuenta_destino')
    search_fields = ('descripcion', 'usuario__username', 'cuenta_origen__nombre', 'cuenta_destino__nombre')
    date_hierarchy = 'fecha'
    autocomplete_fields = ('cuenta_origen', 'cuenta_destino')
    readonly_fields = ('usuario', 'creado_en')
    fields = ('cuenta_origen', 'cuenta_destino', 'monto', 'fecha', 'descripcion', 'usuario', 'creado_en')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)

    def monto_coloreado(self, obj):
        return format_html(
            '<span style="font-weight:bold;">{} → {} = ${}</span>',
            obj.cuenta_origen,
            obj.cuenta_destino,
            f'{obj.monto:,.2f}',
        )
    monto_coloreado.short_description = _('Monto')
    monto_coloreado.admin_order_field = 'monto'

    def descripcion_corta(self, obj):
        return obj.descripcion[:60] + '…' if len(obj.descripcion) > 60 else obj.descripcion
    descripcion_corta.short_description = _('Descripción')


# ---------------------------------------------------------------------------
# Reporte form
# ---------------------------------------------------------------------------

class ReporteCuentaForm(forms.Form):
    medio_de_pago = forms.ModelChoiceField(
        queryset=MedioDePago.objects.all().order_by('nombre'),
        label=_('Cuenta / Medio de pago'),
        widget=forms.Select(attrs={'style': 'width:300px;'}),
    )
    fecha_desde = forms.DateField(
        label=_('Fecha desde'),
        widget=admin.widgets.AdminDateWidget(),
    )
    fecha_hasta = forms.DateField(
        label=_('Fecha hasta'),
        widget=admin.widgets.AdminDateWidget(),
    )

    def clean(self):
        cleaned = super().clean()
        fd = cleaned.get('fecha_desde')
        fh = cleaned.get('fecha_hasta')
        if fd and fh and fd > fh:
            raise forms.ValidationError(_('La fecha desde no puede ser posterior a la fecha hasta.'))
        return cleaned


# ---------------------------------------------------------------------------
# MovimientoCuenta admin (with report view)
# ---------------------------------------------------------------------------

@admin.register(MovimientoCuenta)
class MovimientoCuentaAdmin(admin.ModelAdmin):
    list_display = (
        'fecha', 'tipo', 'signo', 'medio_de_pago',
        'monto', 'usuario', 'turno', 'descripcion',
    )
    list_filter = ('tipo', 'signo', 'medio_de_pago', 'usuario', 'turno')
    search_fields = ('descripcion', 'usuario__username')
    date_hierarchy = 'fecha'
    readonly_fields = (
        'fecha', 'medio_de_pago', 'tipo', 'signo', 'monto',
        'usuario', 'turno', 'descripcion', 'content_type', 'object_id',
    )
    change_list_template = 'admin/tesoreria/movimientocuenta/change_list.html'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow superusers to clean up bad data; movements normally regenerate.
        return request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'reporte/',
                self.admin_site.admin_view(self._reporte_view),
                name='tesoreria_reporte_cuenta',
            ),
        ]
        return custom + urls

    def _reporte_view(self, request):
        from django.utils import timezone
        from .models import MovimientoCuenta as MC

        form = ReporteCuentaForm(request.POST or None)

        if request.method == 'POST' and form.is_valid():
            from .reports import build_pdf, build_excel

            medio = form.cleaned_data['medio_de_pago']
            fecha_desde = form.cleaned_data['fecha_desde']
            fecha_hasta = form.cleaned_data['fecha_hasta']
            formato = request.POST.get('formato', 'pdf')

            # Convert dates to aware datetimes covering full days
            from datetime import datetime, time
            import pytz
            tz = timezone.get_current_timezone()
            dt_desde = timezone.make_aware(datetime.combine(fecha_desde, time.min), tz)
            dt_hasta = timezone.make_aware(datetime.combine(fecha_hasta, time.max), tz)

            movimientos = (
                MC.objects
                .filter(medio_de_pago=medio, fecha__gte=dt_desde, fecha__lte=dt_hasta)
                .select_related('usuario', 'turno')
                .order_by('fecha', 'id')
            )

            nombre_archivo = (
                f"estado_cuenta_{medio.nombre}_{fecha_desde}_{fecha_hasta}"
                .replace(' ', '_')
            )

            if formato == 'excel':
                buffer = build_excel(medio, dt_desde, dt_hasta, movimientos)
                response = HttpResponse(
                    buffer,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.xlsx"'
                return response
            else:
                buffer = build_pdf(medio, dt_desde, dt_hasta, movimientos)
                response = HttpResponse(buffer, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.pdf"'
                return response

        context = {
            **self.admin_site.each_context(request),
            'title': _('Exportar reporte de cuenta'),
            'form': form,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/tesoreria/reporte_cuenta.html', context)
