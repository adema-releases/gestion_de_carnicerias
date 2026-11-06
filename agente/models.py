import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import crypto

PROVEEDOR_CHOICES = (
    ('ollama', 'Ollama (local)'),
    ('openai', 'OpenAI'),
    ('gemini', 'Gemini'),
    ('otro', _('Other')),
)

CANAL_CHOICES = (
    ('panel', _('Integrated panel')),
    ('telegram', 'Telegram'),
    ('api', 'API'),
)

ROL_CHOICES = (
    ('user', _('User')),
    ('assistant', _('Assistant')),
    ('tool', _('Tool')),
    ('system', _('System')),
)

ESTADO_EJECUCION_CHOICES = (
    ('ok', 'OK'),
    ('error', _('Error')),
    ('timeout', _('Timeout')),
    ('limite_excedido', _('Limit exceeded')),
)

ESTADO_TOOL_CHOICES = (
    ('ok', 'OK'),
    ('error', _('Error')),
)


class ConfiguracionAgente(models.Model):
    """Configuración única del agente (mismo patrón que ``core.Configuracion``:
    modelo plano, una sola fila, sin ``django-solo`` real)."""

    activo = models.BooleanField(
        default=False,
        verbose_name=_('Assistant enabled'),
        help_text=_('Master switch. Disabled by default until a provider is configured.'),
    )
    panel_activo = models.BooleanField(
        default=True,
        verbose_name=_('Integrated panel enabled'),
        help_text=_('Shows or hides the assistant button in the POS panel.'),
    )
    proveedor = models.CharField(
        max_length=20,
        choices=PROVEEDOR_CHOICES,
        default='ollama',
        verbose_name=_('Provider'),
        help_text=_('Informational label only — the actual call is always OpenAI-compatible.'),
    )
    base_url = models.CharField(
        max_length=255,
        blank=True,
        default='http://localhost:11434/v1',
        verbose_name=_('Base URL'),
        help_text=_('OpenAI-compatible chat completions endpoint (Ollama, OpenAI, Gemini, etc.).'),
    )
    modelo = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Model'),
        help_text=_(
            'Model name/id sent to the provider, e.g. "gpt-4o-mini". For local Ollama, '
            'a small model with native "tools" support and no hidden reasoning (e.g. '
            '"functiongemma") answers in seconds; reasoning models (the Qwen3 family, '
            'DeepSeek-R1, etc.) can take a minute or more per turn on CPU.'
        ),
    )
    api_key_cifrada = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Encrypted API key'),
        help_text=_('Stored encrypted at rest. Empty for local providers such as Ollama.'),
    )
    temperatura = models.FloatField(
        default=0.2,
        verbose_name=_('Temperature'),
        help_text=_('Kept low on purpose: operational interpretation, not creative writing.'),
    )
    timeout_segundos = models.PositiveIntegerField(
        default=120,
        verbose_name=_('Timeout (seconds)'),
        help_text=_(
            'Maximum time to wait for a single provider call. Small local models on CPU '
            '(especially reasoning models such as Qwen3) can easily take one to two '
            'minutes — keep this high for local providers, lower it for fast paid APIs.'
        ),
    )
    desactivar_razonamiento_extendido = models.BooleanField(
        default=False,
        verbose_name=_('Disable extended reasoning'),
        help_text=_(
            'Appends "/no_think" to the system prompt. Only has an effect on models that '
            'honor that convention (Qwen3 and similar reasoning models). These models '
            'generate a long hidden "thinking" block before every answer by default, '
            'which can take a minute or more on CPU — enable this for a much faster, '
            'more direct assistant at the cost of some reasoning quality.'
        ),
    )
    max_reintentos = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Max retries'),
        help_text=_('Retries on transient network/provider errors before failing the turn.'),
    )
    max_tokens_salida = models.PositiveIntegerField(
        default=1024,
        verbose_name=_('Max output tokens'),
        help_text=_('Upper bound requested from the provider for each response.'),
    )
    max_tool_calls_por_turno = models.PositiveIntegerField(
        default=6,
        verbose_name=_('Max tool calls per turn'),
        help_text=_('Hard limit on the tool-calling loop to avoid runaway iterations.'),
    )
    max_mensajes_historial = models.PositiveIntegerField(
        default=20,
        verbose_name=_('Max history messages'),
        help_text=_('How many recent messages are loaded as conversation context.'),
    )
    costo_por_1k_tokens_entrada = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        verbose_name=_('Cost per 1K input tokens'),
        help_text=_('Optional, used only to estimate spend on paid providers. Leave empty for Ollama.'),
    )
    costo_por_1k_tokens_salida = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        verbose_name=_('Cost per 1K output tokens'),
        help_text=_('Optional, used only to estimate spend on paid providers. Leave empty for Ollama.'),
    )

    def set_api_key(self, raw_api_key: str) -> None:
        self.api_key_cifrada = crypto.encrypt_api_key(raw_api_key or '')

    def get_api_key(self) -> str:
        return crypto.decrypt_api_key(self.api_key_cifrada)

    def clean(self):
        super().clean()
        # Mientras el asistente esté activo, una URL base o modelo vacíos
        # no son un estado válido: el chat va a fallar en cada mensaje. Se
        # valida acá (no solo en la vista de detectar modelos) para que
        # tampoco se pueda guardar así desde el admin.
        if not self.activo:
            return
        errores = {}
        if not self.base_url:
            errores['base_url'] = _('Required while the assistant is enabled.')
        elif not self.base_url.lower().startswith(('http://', 'https://')):
            errores['base_url'] = _('Must start with http:// or https://.')
        if not self.modelo:
            errores['modelo'] = _('Required while the assistant is enabled.')
        if errores:
            raise ValidationError(errores)

    def esta_listo_para_usarse(self) -> bool:
        return bool(
            self.activo and self.base_url
            and self.base_url.lower().startswith(('http://', 'https://'))
            and self.modelo
        )

    def __str__(self):
        return f'Configuración del agente ({self.proveedor})'

    class Meta:
        verbose_name = _('Assistant configuration')
        verbose_name_plural = _('Assistant configuration')


class Conversacion(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conversaciones_agente', verbose_name=_('User'),
        help_text=_('User who owns this conversation.'),
    )
    canal = models.CharField(
        max_length=20, choices=CANAL_CHOICES, default='panel',
        verbose_name=_('Channel'), help_text=_('Channel this conversation came from.'),
    )
    creada = models.DateTimeField(default=timezone.now, verbose_name=_('Created at'))
    activa = models.BooleanField(default=True, verbose_name=_('Active'))

    def __str__(self):
        return f'Conversación #{self.pk} ({self.canal})'

    class Meta:
        verbose_name = _('Conversation')
        verbose_name_plural = _('Conversations')
        ordering = ('-creada',)


class Mensaje(models.Model):
    conversacion = models.ForeignKey(
        Conversacion, on_delete=models.CASCADE, related_name='mensajes',
        verbose_name=_('Conversation'),
    )
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, verbose_name=_('Role'))
    contenido = models.TextField(verbose_name=_('Content'))
    creado = models.DateTimeField(default=timezone.now, verbose_name=_('Created at'))

    def __str__(self):
        return f'{self.rol}: {self.contenido[:60]}'

    class Meta:
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')
        ordering = ('creado',)
        indexes = [models.Index(fields=['conversacion', 'creado'])]


class Ejecucion(models.Model):
    """Una vuelta completa del orquestador: mensaje entrante -> mensaje saliente."""

    conversacion = models.ForeignKey(
        Conversacion, on_delete=models.CASCADE, related_name='ejecuciones',
        verbose_name=_('Conversation'),
    )
    mensaje_entrada = models.ForeignKey(
        Mensaje, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ejecuciones_como_entrada', verbose_name=_('Input message'),
    )
    mensaje_salida = models.ForeignKey(
        Mensaje, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ejecuciones_como_salida', verbose_name=_('Output message'),
    )
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    proveedor = models.CharField(max_length=20, blank=True, default='', verbose_name=_('Provider'))
    modelo = models.CharField(max_length=100, blank=True, default='', verbose_name=_('Model'))
    estado = models.CharField(
        max_length=20, choices=ESTADO_EJECUCION_CHOICES, default='ok', verbose_name=_('Status'),
    )
    duracion_ms = models.PositiveIntegerField(default=0, verbose_name=_('Duration (ms)'))
    tokens_prompt = models.PositiveIntegerField(default=0, verbose_name=_('Prompt tokens'))
    tokens_completion = models.PositiveIntegerField(default=0, verbose_name=_('Completion tokens'))
    costo_estimado = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True, verbose_name=_('Estimated cost'),
    )
    error_saneado = models.TextField(
        blank=True, default='', verbose_name=_('Sanitized error'),
        help_text=_('Truncated error text with no secrets or raw tracebacks.'),
    )
    creada = models.DateTimeField(default=timezone.now, verbose_name=_('Created at'))

    def __str__(self):
        return f'Ejecución #{self.pk} ({self.estado})'

    class Meta:
        verbose_name = _('Execution')
        verbose_name_plural = _('Executions')
        ordering = ('-creada',)


class ToolInvocacion(models.Model):
    ejecucion = models.ForeignKey(
        Ejecucion, on_delete=models.CASCADE, related_name='tool_invocaciones',
        verbose_name=_('Execution'),
    )
    tool_name = models.CharField(max_length=100, verbose_name=_('Tool name'))
    tool_version = models.CharField(max_length=20, default='1', verbose_name=_('Tool version'))
    argumentos = models.JSONField(default=dict, blank=True, verbose_name=_('Arguments'))
    resultado = models.JSONField(default=dict, blank=True, verbose_name=_('Result'))
    estado = models.CharField(
        max_length=20, choices=ESTADO_TOOL_CHOICES, default='ok', verbose_name=_('Status'),
    )
    duracion_ms = models.PositiveIntegerField(default=0, verbose_name=_('Duration (ms)'))
    error_saneado = models.TextField(blank=True, default='', verbose_name=_('Sanitized error'))
    creada = models.DateTimeField(default=timezone.now, verbose_name=_('Created at'))

    def __str__(self):
        return f'{self.tool_name} ({self.estado})'

    class Meta:
        verbose_name = _('Tool invocation')
        verbose_name_plural = _('Tool invocations')
        ordering = ('-creada',)


def get_config() -> ConfiguracionAgente:
    """Fila única de configuración, creada perezosamente si no existe.

    Mismo patrón que ``core.Configuracion``: no hay constraint de DB que
    fuerce una sola fila, solo la disciplina de acceder siempre por acá.
    """
    return ConfiguracionAgente.objects.first() or ConfiguracionAgente.objects.create()
