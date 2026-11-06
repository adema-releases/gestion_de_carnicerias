from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from solo.admin import SingletonModelAdmin

from .models import ConfiguracionAgente, Conversacion, Ejecucion, Mensaje, ToolInvocacion


class ConfiguracionAgenteForm(forms.ModelForm):
    api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_('API key'),
        help_text=_('Encrypted on save. Leave blank to keep the current key unchanged.'),
    )

    class Meta:
        model = ConfiguracionAgente
        exclude = ('api_key_cifrada',)

    def save(self, commit=True):
        instancia = super().save(commit=False)
        nueva_api_key = self.cleaned_data.get('api_key')
        if nueva_api_key:
            instancia.set_api_key(nueva_api_key)
        if commit:
            instancia.save()
        return instancia


@admin.register(ConfiguracionAgente)
class ConfiguracionAgenteAdmin(SingletonModelAdmin):
    form = ConfiguracionAgenteForm

    class Media:
        js = ('js/admin-agente-modelos.js',)

    fieldsets = (
        (_('Status'), {'fields': ('activo', 'panel_activo')}),
        (_('Provider'), {
            'description': _(
                'For a local Ollama provider, prefer small models with native tool-calling '
                'support and no hidden reasoning (e.g. "functiongemma", "qwen2.5:3b-instruct", '
                '"llama3.2:3b") if you don\'t have a GPU. Reasoning models — the whole Qwen3 '
                'family (including "-vl" variants), DeepSeek-R1, etc. — generate a long hidden '
                '"thinking" block before every answer and can take one to two minutes per turn '
                'on CPU, sometimes exhausting the token limit before producing any visible text. '
                'For OpenAI, "Detect models" only lists actual chat models (voice/image/'
                'embedding/legacy ones are hidden) and marks a suggested default — "gpt-4o-mini" '
                'is a solid balance of cost, speed and tool-calling quality for this kind of '
                'assistant; reach for "gpt-4o"/"gpt-4.1" only if you hit quality issues.'
            ),
            'fields': ('proveedor', 'base_url', 'modelo', 'api_key'),
        }),
        (_('Limits'), {'fields': (
            'temperatura', 'timeout_segundos', 'max_reintentos', 'max_tokens_salida',
            'max_tool_calls_por_turno', 'max_mensajes_historial', 'desactivar_razonamiento_extendido',
        )}),
        (_('Estimated cost'), {'fields': ('costo_por_1k_tokens_entrada', 'costo_por_1k_tokens_salida')}),
    )


class SoloLecturaAdminMixin:
    """Los registros de conversación/ejecución son un rastro de auditoría:
    se pueden ver y filtrar desde el admin, pero no editar ni crear a mano."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MensajeInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = Mensaje
    extra = 0
    can_delete = False
    fields = ('rol', 'contenido', 'creado')
    readonly_fields = fields


class ToolInvocacionInline(SoloLecturaAdminMixin, admin.TabularInline):
    model = ToolInvocacion
    extra = 0
    can_delete = False
    fields = ('tool_name', 'tool_version', 'estado', 'argumentos', 'resultado', 'duracion_ms', 'error_saneado')
    readonly_fields = fields


@admin.register(Conversacion)
class ConversacionAdmin(SoloLecturaAdminMixin, ImportExportModelAdmin):
    list_display = ('id', 'usuario', 'canal', 'creada', 'activa')
    list_filter = ('canal', 'activa')
    date_hierarchy = 'creada'
    search_fields = ('usuario__username',)
    inlines = [MensajeInline]


@admin.register(Ejecucion)
class EjecucionAdmin(SoloLecturaAdminMixin, ImportExportModelAdmin):
    list_display = (
        'id', 'conversacion', 'estado', 'proveedor', 'modelo',
        'duracion_ms', 'tokens_prompt', 'tokens_completion', 'costo_estimado', 'creada',
    )
    list_filter = ('estado', 'proveedor')
    date_hierarchy = 'creada'
    search_fields = ('conversacion__usuario__username', 'correlation_id')
    inlines = [ToolInvocacionInline]
