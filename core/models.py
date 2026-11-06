from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal, InvalidOperation

from core.roles import ROLES, aplicar_rol
from core.sync import DeSucursalMixin, IdentidadGlobalMixin

# Idiomas en que se puede ver el sistema. Cada nombre va en su propio idioma
# para que quien no lee el actual encuentre el suyo. Debe coincidir con
# settings.LANGUAGES.
IDIOMA_POR_DEFECTO = 'es'
IDIOMAS = [
    ('es', 'Español'),
    ('zh-hans', '中文'),
]

# NOTE: ``MedioDePago`` was moved to the ``tesoreria`` app. The legacy
# ``MediosDePago`` choice tuple is kept there as well. Import from
# ``tesoreria.models`` if you need to reference payment methods.


class Sucursal(IdentidadGlobalMixin):
    """Carnicería del frigorífico, en un local alquilado dentro de un supermercado.

    El depósito central (donde se reciben las medias reses y se desposta) también
    es una sucursal, de tipo depósito. Las demás son sus clientes internos: lo que
    el depósito les entrega es una transferencia, no una venta externa.
    """
    TIPO_DEPOSITO = 'deposito'
    TIPO_SUCURSAL = 'sucursal'
    TIPOS = [
        (TIPO_DEPOSITO, _('Depósito central')),
        (TIPO_SUCURSAL, _('Sucursal (cliente interno)')),
    ]

    codigo = models.CharField(
        max_length=20, unique=True,
        verbose_name=_("Código"),
        help_text=_("Código corto y único de la sucursal, por ejemplo S001."),
    )
    nombre = models.CharField(
        max_length=120,
        verbose_name=_("Nombre"),
        help_text=_("Nombre con el que se reconoce la sucursal."),
    )
    tipo = models.CharField(
        max_length=10, choices=TIPOS, default=TIPO_SUCURSAL,
        verbose_name=_("Tipo"),
        help_text=_("Depósito central: recibe, desposta y distribuye. Sucursal: vende al público y recibe del depósito como cliente interno (transferencias, no ventas)."),
    )
    supermercado = models.CharField(
        max_length=150, blank=True,
        verbose_name=_("Supermercado"),
        help_text=_("Supermercado donde está el local alquilado."),
    )
    direccion = models.CharField(
        max_length=255, blank=True,
        verbose_name=_("Dirección"),
        help_text=_("Calle, número y localidad."),
    )
    activa = models.BooleanField(
        default=True,
        verbose_name=_("Activa"),
        help_text=_("Las sucursales inactivas no operan."),
    )
    token_sync = models.CharField(
        max_length=64, blank=True, db_index=True,
        verbose_name=_("Token de sincronización"),
        help_text=_("Clave con la que la PC de la sucursal se identifica ante la central. Va en SYNC_TOKEN del .env de la sucursal."),
    )
    ultima_sync = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Última sincronización"),
        help_text=_("Última vez que la sucursal subió o bajó datos (solo en la central)."),
    )

    def save(self, *args, **kwargs):
        if not self.token_sync:
            import secrets
            self.token_sync = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    class Meta:
        verbose_name = _("Sucursal")
        verbose_name_plural = _("Sucursales")
        ordering = ('codigo',)


class Puesto(DeSucursalMixin):
    """Dispositivo de trabajo de la sucursal: una caja, un mostrador o la recepción."""
    TIPO_CAJA = 'caja'
    TIPO_MOSTRADOR = 'mostrador'
    TIPO_RECEPCION = 'recepcion'
    TIPOS = [
        (TIPO_CAJA, _('Caja')),
        (TIPO_MOSTRADOR, _('Mostrador')),
        (TIPO_RECEPCION, _('Recepción')),
    ]

    nombre = models.CharField(
        max_length=60,
        verbose_name=_("Nombre"),
        help_text=_("Nombre visible del puesto, por ejemplo Mostrador 1."),
    )
    tipo = models.CharField(
        max_length=12, choices=TIPOS,
        verbose_name=_("Tipo"),
        help_text=_("Define qué pantalla se abre en el dispositivo de este puesto."),
    )
    activo = models.BooleanField(
        default=True,
        verbose_name=_("Activo"),
        help_text=_("Los puestos inactivos no se pueden elegir."),
    )
    impresora = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name=_("Impresora"),
        help_text=_("Nombre exacto de la impresora térmica en Windows de la PC donde corre el sistema (ej: POS80). En el mostrador imprime la comanda para el cliente. Vacío = la impresora de la Configuración."),
    )
    ancho_papel = models.PositiveSmallIntegerField(
        choices=[(58, '58 mm'), (80, '80 mm')], default=80,
        verbose_name=_("Ancho del papel"),
        help_text=_("Ancho del rollo de la impresora de este puesto."),
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = _("Puesto")
        verbose_name_plural = _("Puestos")
        ordering = ('tipo', 'nombre')


class Configuracion(models.Model):
    IMPORTES_RAPIDOS_VENTA_DEFAULT = (Decimal('500'), Decimal('1000'), Decimal('2000'), Decimal('5000'))

    nombre    = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Company name"),
        help_text=_("Commercial name or legal business name."),
    )
    direccion = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Address"),
        help_text=_("Street, number, city, and state or province."),
    )
    telefono  = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Contact phone"),
        help_text=_("Area code and phone number."),
    )
    instagram = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Instagram"),
        help_text=_("Instagram username or URL."),
    )
    facebook = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Facebook"),
        help_text=_("Facebook page or URL."),
    )
    whatsapp = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("WhatsApp"),
        help_text=_("WhatsApp number including country code."),
    )
    sitio_web = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Website"),
        help_text=_("Business website URL."),
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Description"),
        help_text=_("Short business description."),
    )
    nombre_impresora = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("POS printer name"),
        help_text=_(
            "Nombre exacto de la impresora térmica en Windows "
            "(ej: \"Xprinter XP-80\"). "
            "Dejá en blanco para imprimir desde el navegador."
        ),
    )
    permitir_turnos_multi_dia = models.BooleanField(
        default=True,
        verbose_name=_("Allow multi-day register shifts"),
        help_text=_(
            "Si está activo, un turno abierto puede seguir vigente después de las 00:00. "
            "Si se desactiva, el cajero debe cerrar caja al cambiar el día local."
        ),
    )
    importes_rapidos_venta = models.CharField(
        max_length=255,
        blank=True,
        default='500,1000,2000,5000',
        verbose_name=_("Importes rápidos de venta"),
        help_text=_("Importes favoritos del modal de venta rápida, separados por coma. Ej: 500,1000,2000,5000."),
    )

    cobro_automatico_deudas = models.BooleanField(
        default=False,
        verbose_name=_("Cobro automático de deudas"),
        help_text=_(
            "Si está activo, al recibir un adelanto se aplicará automáticamente "
            "para cancelar las deudas (saldos iniciales o ventas fiadas) más antiguas del cliente."
        ),
    )
    pago_automatico_deudas_proveedores = models.BooleanField(
        default=False,
        verbose_name=_("Pago automático de deudas a proveedores"),
        help_text=_(
            "Si está activo, al registrar un adelanto a proveedor se aplicará automáticamente "
            "para cancelar las deudas más antiguas que se posean con el mismo."
        ),
    )
    compensar_deudas_mas_antiguas_primero = models.BooleanField(
        default=True,
        verbose_name=_("Compensar deudas más antiguas primero"),
        help_text=_(
            "Si está activo, la compensación usa orden cronológico estricto y "
            "no intenta deudas posteriores si una deuda anterior no puede cubrirse completa. "
            "Si se desactiva, puede saltear deudas anteriores no cubribles para compensar "
            "deudas posteriores siempre que se cubran completas (sin parciales)."
        ),
    )
    ticket_cc_mostrar_importe_pendiente = models.BooleanField(
        default=False,
        verbose_name=_("Ticket CC: mostrar importe pendiente"),
        help_text=_(
            "Si está activo, el ticket de estado de cuenta muestra tanto el importe original "
            "como el importe pendiente por cada deuda. Si se desactiva, solo muestra el importe original, "
            "ahorrando espacio en el ticket."
        ),
    )

    sucursal = models.ForeignKey(
        Sucursal, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        verbose_name=_("Sucursal de esta instalación"),
        help_text=_("Sucursal a la que pertenecen todas las operaciones registradas en esta PC."),
    )

    DIAS_SEMANA = [
        (0, _('Lunes')), (1, _('Martes')), (2, _('Miércoles')), (3, _('Jueves')),
        (4, _('Viernes')), (5, _('Sábado')), (6, _('Domingo')),
    ]
    dia_liquidacion = models.PositiveSmallIntegerField(
        choices=DIAS_SEMANA, default=1,
        verbose_name=_("Día de liquidación"),
        help_text=_("Día de la semana en que se tira lo viejo, se cuenta todo y se cierra el balance de kilos."),
    )

    sync_cursor_bajada = models.BigIntegerField(
        default=0,
        verbose_name=_("Cursor de bajada"),
        help_text=_("Último cambio de la central ya aplicado en esta sucursal."),
    )
    sync_ultima = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Última sincronización"),
        help_text=_("Última sincronización completa con la central."),
    )
    sync_ultimo_error = models.CharField(
        max_length=500, blank=True,
        verbose_name=_("Último error de sincronización"),
        help_text=_("Vacío si la última sincronización salió bien."),
    )

    # ── Tesorería: cuentas del sistema ──────────────────────────────────────
    cuenta_caja_pos = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_("Cuenta caja POS (drawer)"),
        help_text=_(
            "Cuenta Efectivo que representa el cajón físico de la terminal. "
            "Recibe el fondo inicial al abrir turno y queda en $0 tras cada cierre. "
            "Si se deja vacío se usa la primera cuenta Efectivo del sistema."
        ),
    )
    cuenta_caja_central = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_("Cuenta caja central"),
        help_text=_(
            "Cuenta Efectivo donde vive el dinero fuera de los turnos (tesorería/caja fuerte). "
            "Es el origen por defecto del fondo de apertura y el destino del efectivo declarado al cierre."
        ),
    )
    cuenta_diferencias_caja = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_("Cuenta diferencias de caja"),
        help_text=_(
            "Cuenta virtual que acumula faltantes/sobrantes de arqueo al cierre de cada turno "
            "(el 'ticket de diferencia'). Saldo positivo = faltantes a regularizar con Ajustes de cuenta."
        ),
    )
    cuenta_mercado_pago = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_("Cuenta Mercado Pago"),
        help_text=_(
            "Cuenta usada para el control informativo de Mercado Pago en apertura/cierre de caja. "
            "Si se deja vacío se busca por nombre 'Mercado Pago'."
        ),
    )

    # ── Apertura de caja: cuenta de origen ─────────────────────────────────
    cuenta_origen_apertura_default = models.ForeignKey(
        'tesoreria.MedioDePago',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_("Cuenta de origen por defecto (apertura)"),
        help_text=_(
            "Cuenta desde donde se extrae el efectivo inicial al abrir caja (ej: RESERVA, CAJA FUERTE). "
            "No puede ser la misma cuenta caja POS. "
            "Si se deja vacío se usa la cuenta caja central."
        ),
    )
    cajero_puede_cambiar_cuenta_origen = models.BooleanField(
        default=True,
        verbose_name=_("Cajero puede cambiar la cuenta de origen"),
        help_text=_(
            "Si está activo, el cajero ve el selector de cuenta de origen y puede cambiarlo. "
            "Si se desactiva, el selector queda oculto y se usa siempre la cuenta por defecto "
            "(sin opción de modificar). La cuenta de origen es siempre obligatoria si se declara efectivo."
        ),
    )

    def clean(self):
        super().clean()
        self._parse_importes_rapidos_venta(validate=True)
        for campo in ('cuenta_caja_pos', 'cuenta_caja_central', 'cuenta_origen_apertura_default'):
            cuenta = getattr(self, campo, None)
            if cuenta and cuenta.categoria != 'Efectivo':
                raise ValidationError({
                    campo: _("Solo se permite una cuenta de tipo Efectivo."),
                })
        if self.cuenta_caja_pos_id:
            duplicadas = {
                'cuenta_caja_central': self.cuenta_caja_central_id,
                'cuenta_diferencias_caja': self.cuenta_diferencias_caja_id,
                'cuenta_origen_apertura_default': self.cuenta_origen_apertura_default_id,
            }
            for campo, cuenta_id in duplicadas.items():
                if cuenta_id and cuenta_id == self.cuenta_caja_pos_id:
                    raise ValidationError({
                        campo: _("No puede ser la misma cuenta que la caja POS (drawer)."),
                    })

    def _parse_importes_rapidos_venta(self, validate=False):
        raw = (self.importes_rapidos_venta or '').strip()
        if not raw:
            return list(self.IMPORTES_RAPIDOS_VENTA_DEFAULT)
        values = []
        for part in raw.split(','):
            text = part.strip().replace(' ', '')
            if not text:
                continue
            if '.' in text and all(len(group) == 3 for group in text.split('.')[1:]):
                text = text.replace('.', '')
            try:
                value = Decimal(text)
            except (InvalidOperation, ValueError):
                if validate:
                    raise ValidationError({'importes_rapidos_venta': _('Usá solo números separados por coma.')})
                continue
            if value <= 0:
                if validate:
                    raise ValidationError({'importes_rapidos_venta': _('Los importes rápidos deben ser mayores a cero.')})
                continue
            values.append(value)
        if not values:
            if validate:
                raise ValidationError({'importes_rapidos_venta': _('Ingresá al menos un importe válido o dejá el campo vacío.')})
            return list(self.IMPORTES_RAPIDOS_VENTA_DEFAULT)
        return values

    def get_importes_rapidos_venta(self):
        return self._parse_importes_rapidos_venta(validate=False)

    def __str__(self):
        return self.nombre or str(_("Unnamed configuration"))

    class Meta:
        verbose_name = _("Configuration")
        verbose_name_plural = _("Configurations")
    # Se mantiene manager por compatibilidad con el resto del proyecto.
    objects = models.Manager()


class UserProfile(models.Model):
    """Adds contact details to Django's built-in user model."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_("User"),
        help_text=_("User account linked to this profile."),
    )
    telefono = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Phone"),
        help_text=_("Optional contact phone number."),
    )
    nombre_completo = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Full name"),
        help_text=_("Person's full display name."),
    )
    rol = models.CharField(
        max_length=12, choices=ROLES, blank=True,
        verbose_name=_("Rol"),
        help_text=_("Al elegir o cambiar el rol se cargan sus permisos de POS."),
    )
    puestos = models.ManyToManyField(
        Puesto, blank=True, related_name='usuarios',
        verbose_name=_("Puestos habilitados"),
        help_text=_("Puestos donde puede operar. Vacío = todos los de la sucursal."),
    )
    idioma = models.CharField(
        max_length=10,
        choices=IDIOMAS,
        default=IDIOMA_POR_DEFECTO,
        verbose_name=_("Idioma"),
        help_text=_("Idioma en que esta persona ve el sistema. Lo puede cambiar desde el POS."),
    )

    def save(self, *args, **kwargs):
        rol_anterior = None
        if self.pk:
            rol_anterior = UserProfile.objects.filter(pk=self.pk).values_list('rol', flat=True).first()
        super().save(*args, **kwargs)
        if self.rol and self.rol != rol_anterior:
            aplicar_rol(self.user, self.rol)

    def __str__(self):
        return self.nombre_completo or self.user.username

    class Meta:
        verbose_name = _("User profile")
        verbose_name_plural = _("User profiles")


class PermisosCajero(models.Model):
    """Stores granular POS permissions for cashier users."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='permisos_cajero',
        verbose_name=_("User"),
        help_text=_("Cashier user affected by these permissions."),
    )
    puede_registrar_venta = models.BooleanField(default=True, verbose_name=_("Register sale"), help_text=_("Allows the user to create POS sales."))
    puede_registrar_gasto = models.BooleanField(default=True, verbose_name=_("Register expense"), help_text=_("Allows the user to record business expenses."))
    puede_pagar_proveedor = models.BooleanField(default=True, verbose_name=_("Pay supplier or settle account"), help_text=_("Allows supplier payments and supplier debt settlement."))
    puede_registrar_retiro = models.BooleanField(default=True, verbose_name=_("Withdraw cash"), help_text=_("Allows cash withdrawals from the register."))
    puede_cobrar_deuda_cliente = models.BooleanField(default=True, verbose_name=_("Collect customer debt"), help_text=_("Allows customer current-account debt collection."))
    puede_registrar_adelanto_cliente = models.BooleanField(default=True, verbose_name=_("Registrar adelanto de cliente"), help_text=_("Permite registrar adelantos de clientes desde el POS."))
    puede_registrar_adelanto_proveedor = models.BooleanField(default=True, verbose_name=_("Registrar adelanto a proveedor"), help_text=_("Permite registrar adelantos a proveedores desde el POS."))
    puede_crear_editar_cliente = models.BooleanField(default=True, verbose_name=_("Create or edit customers"), help_text=_("Allows customer creation and updates from the POS."))
    puede_crear_editar_proveedor = models.BooleanField(default=True, verbose_name=_("Create or edit suppliers"), help_text=_("Allows supplier creation and updates from the POS."))
    puede_crear_categoria_venta = models.BooleanField(default=True, verbose_name=_("Create sale categories"), help_text=_("Allows creation of inventory categories from the POS."))
    puede_abrir_cerrar_caja = models.BooleanField(default=True, verbose_name=_("Open or close register"), help_text=_("Allows opening and closing cash register shifts."))
    usar_flujo_venta_guiado = models.BooleanField(default=False, verbose_name=_("Use guided sale flow"), help_text=_("Shows the simplified step-by-step sale modal in the POS."))
    puede_armar_comanda = models.BooleanField(default=True, verbose_name=_("Armar comandas"), help_text=_("Permite cargar comandas en el mostrador para que la caja las cobre."))
    puede_recibir_mercaderia = models.BooleanField(default=False, verbose_name=_("Recibir mercadería"), help_text=_("Permite cargar remitos y pesar medias reses."))
    puede_despostar = models.BooleanField(default=False, verbose_name=_("Despostar"), help_text=_("Permite registrar el desposte de una media res."))
    puede_ver_stock = models.BooleanField(default=False, verbose_name=_("Ver stock"), help_text=_("Permite ver el stock por corte y las medias reses en cámara."))
    puede_anular_comanda = models.BooleanField(default=False, verbose_name=_("Anular comandas de otros"), help_text=_("Permite anular comandas abiertas armadas por otra persona. Cada uno puede anular las propias."))
    puede_contar_stock = models.BooleanField(default=False, verbose_name=_("Contar stock"), help_text=_("Permite cargar lo que queda y lo que se tira en conteos y liquidaciones, sin ver el stock esperado."))
    puede_cerrar_conteo = models.BooleanField(default=False, verbose_name=_("Cerrar conteos y liquidaciones"), help_text=_("Permite ver las diferencias contra el stock esperado y cerrar el conteo, lo que ajusta el stock."))

    def __str__(self):
        return str(_("Permissions for %(username)s") % {'username': self.user.username})

    class Meta:
        verbose_name = _("Cashier permissions")
        verbose_name_plural = _("Cashier permissions")


class CambioSync(models.Model):
    """Cola de cambios por sincronizar.

    En la sucursal anota sus operaciones para subirlas; en la central anota
    catálogo, precios, plantillas y despachos para que las sucursales los bajen.
    Se guarda solo modelo + uuid: el contenido se lee al momento de enviar.
    """
    OP_GUARDAR = 'guardar'
    OP_BORRAR = 'borrar'

    modelo = models.CharField(max_length=60, verbose_name=_("Modelo"), help_text=_("app.modelo del registro cambiado."))
    uuid = models.UUIDField(db_index=True, verbose_name=_("Identificador global"), help_text=_("Registro cambiado."))
    operacion = models.CharField(max_length=10, verbose_name=_("Operación"), help_text=_("guardar o borrar."))
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name=_("Creado en"), help_text=_("Momento del cambio."))

    def __str__(self):
        return f'{self.operacion} {self.modelo} {self.uuid}'

    class Meta:
        verbose_name = _("Cambio por sincronizar")
        verbose_name_plural = _("Cambios por sincronizar")
        ordering = ('id',)
