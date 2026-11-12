import io
import os
import re
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as ImagenPIL

from .balanza import (
    generar_archivo_balanza,
    nombres_repetidos,
    precio_balanza,
    productos_para_balanza,
    texto_balanza,
)
from .lista_precios import (
    _colores_por_seccion,
    agrupar_por_seccion,
    elegir_diseno,
    formato_precio,
    generar_lista_precios,
    repartir,
)
from .models import Categoria, Producto


def paginas_pdf(pdf):
    return len(re.findall(rb'/Type /Page\b', pdf))


class TextoBalanzaTests(TestCase):
    def test_saca_tildes_y_enie(self):
        self.assertEqual(texto_balanza('Entraña'), 'Entrana')
        self.assertEqual(texto_balanza('Chinchulín'), 'Chinchulin')

    def test_recorta_a_18_caracteres(self):
        self.assertEqual(texto_balanza('Achuras y menudencias'), 'Achuras y menudenc')

    def test_no_deja_punto_y_coma(self):
        self.assertNotIn(';', texto_balanza('Tomate; de estación'))

    def test_precio_entero_con_redondeo_comercial(self):
        self.assertEqual(precio_balanza(Decimal('13900.00')), 13900)
        self.assertEqual(precio_balanza(Decimal('1234.50')), 1235)


class ArchivoBalanzaTests(TestCase):
    def setUp(self):
        self.vacuno = Categoria.objects.create(nombre='Carne vacuna')
        self.almacen = Categoria.objects.create(nombre='Almacén')

    def producto(self, nombre, codigo, precio='1000', unidad=Producto.UNIDAD_KG, **extra):
        categoria = extra.pop('categoria', self.vacuno)
        return Producto.objects.create(
            nombre=nombre, codigo=codigo, precio=Decimal(precio),
            unidad=unidad, categoria=categoria, **extra,
        )

    def test_lineas_en_formato_systel_max(self):
        self.producto('Entraña', '604', '16800.00')
        self.producto('Bolsa de hueso', '630', '1200', unidad=Producto.UNIDAD_UNIDAD, categoria=self.almacen)
        incluidos, _ = productos_para_balanza()

        contenido = generar_archivo_balanza(incluidos).decode('cp1252')

        self.assertEqual(contenido, (
            'Carne vacuna;604;Entrana;604;16800;0;PESO;0;\r\n'
            'Almacen;630;Bolsa de hueso;630;1200;0;UNIDAD;0;\r\n'
        ))

    def test_ordena_por_plu_numerico(self):
        self.producto('Lomo', '606')
        self.producto('Grasa', '28')
        incluidos, _ = productos_para_balanza()
        self.assertEqual([p.codigo for p in incluidos], ['28', '606'])

    def test_omite_inactivos_sin_codigo_y_codigos_invalidos(self):
        self.producto('Asado', '601')
        self.producto('Nalga', '')
        self.producto('Combo', 'A12')
        self.producto('Otro', '8001')
        self.producto('Viejo', '602', activo=False)

        incluidos, omitidos = productos_para_balanza()

        self.assertEqual([p.codigo for p in incluidos], ['601'])
        self.assertEqual(sorted(p.nombre for p, _ in omitidos), ['Combo', 'Nalga', 'Otro'])

    def test_detecta_nombres_que_quedan_iguales_al_recortar(self):
        a = self.producto('Medallón de pollo Grangys', '671')
        b = self.producto('Medallón de pollo relleno Grangys', '672')
        self.assertEqual(nombres_repetidos([a, b]), {'MEDALLON DE POLLO': ['671', '672']})


class ArchivoBalanzaAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='admin-balanza', password='clave')
        self.client.force_login(self.admin)
        self.categoria = Categoria.objects.create(nombre='Vacuno')
        self.asado = Producto.objects.create(
            nombre='Asado', codigo='601', precio=Decimal('13900'), categoria=self.categoria,
        )
        self.url_archivo = reverse('admin:inventario_producto_archivo_balanza')

    def test_descarga_archivo_con_nombre_fijo(self):
        response = self.client.get(self.url_archivo)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="productos_balanza.csv"')
        self.assertEqual(response.content, b'Vacuno;601;Asado;601;13900;0;PESO;0;\r\n')

    def test_la_lista_de_productos_muestra_el_boton(self):
        response = self.client.get(reverse('admin:inventario_producto_changelist'))
        self.assertContains(response, self.url_archivo)

    def test_usuario_sin_permiso_no_descarga(self):
        User.objects.create_user(username='sin-permiso', password='clave', is_staff=True)
        self.client.login(username='sin-permiso', password='clave')
        response = self.client.get(self.url_archivo)
        self.assertEqual(response.status_code, 403)

    def test_cambiar_precio_avisa_que_la_balanza_quedo_desactualizada(self):
        url = reverse('admin:inventario_producto_change', args=[self.asado.pk])
        response = self.client.post(url, {
            'nombre': 'Asado', 'categoria': self.categoria.pk, 'unidad': 'kg',
            'precio': '14500', 'activo': 'on', 'codigo': '601', 'codigo_barras': '',
        })

        self.assertEqual(response.status_code, 302)
        avisos = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any(self.url_archivo in aviso for aviso in avisos), avisos)

    def test_cambio_que_no_va_a_la_balanza_no_avisa(self):
        url = reverse('admin:inventario_producto_change', args=[self.asado.pk])
        response = self.client.post(url, {
            'nombre': 'Asado', 'categoria': self.categoria.pk, 'unidad': 'kg',
            'precio': '13900', 'activo': 'on', 'codigo': '601', 'codigo_barras': '7790001',
        })

        self.assertEqual(response.status_code, 302)
        avisos = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertFalse(any(self.url_archivo in aviso for aviso in avisos), avisos)

    def test_avisa_productos_que_no_van_a_la_balanza(self):
        Producto.objects.create(nombre='Nalga', precio=Decimal('9000'), categoria=self.categoria)
        response = self.client.get(self.url_archivo)
        avisos = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('Nalga' in aviso for aviso in avisos), avisos)


class ListaPreciosTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Vacuno')

    def crear_productos(self, cantidad):
        Producto.objects.bulk_create([
            Producto(nombre=f'Corte número {i}', codigo=str(600 + i), precio=Decimal('12500'), categoria=self.categoria)
            for i in range(1, cantidad + 1)
        ])

    def test_formato_de_precio_argentino(self):
        self.assertEqual(formato_precio(Decimal('13900')), '$ 13.900')
        self.assertEqual(formato_precio(Decimal('1234.50')), '$ 1.234,50')

    def test_cien_productos_entran_en_una_hoja(self):
        self.crear_productos(100)
        self.assertEqual(paginas_pdf(generar_lista_precios()), 1)

    def secciones(self, *cantidades):
        """Secciones en memoria: (nombre, productos) con la cantidad pedida de cada una."""
        resultado, plu = [], 600
        for numero, cantidad in enumerate(cantidades, start=1):
            productos = []
            for _ in range(cantidad):
                plu += 1
                productos.append(Producto(nombre=f'Corte {plu}', codigo=str(plu), precio=Decimal('9000'), categoria=self.categoria))
            resultado.append((f'Sección {numero}', productos))
        return resultado

    def test_con_pocos_productos_usa_letra_grande_y_una_columna(self):
        columnas, tamano, _ = elegir_diseno(self.secciones(5, 5), 540, 560)
        self.assertEqual(columnas, 1)
        self.assertEqual(tamano, 13)

    def test_con_muchos_productos_reparte_en_columnas(self):
        columnas, _, _ = elegir_diseno(self.secciones(40, 40, 40), 540, 560)
        self.assertGreater(columnas, 1)

    def test_agrupa_por_seccion_en_orden_de_plu_y_productos_por_nombre(self):
        cerdo = Categoria.objects.create(nombre='Cerdo')
        Producto.objects.create(nombre='Bondiola', codigo='662', precio=Decimal('9400'), categoria=cerdo)
        Producto.objects.create(nombre='Vacío', codigo='602', precio=Decimal('12500'), categoria=self.categoria)
        Producto.objects.create(nombre='Asado', codigo='601', precio=Decimal('13900'), categoria=self.categoria)
        productos, _ = productos_para_balanza()

        secciones = agrupar_por_seccion(productos)

        self.assertEqual(
            [(nombre, [p.nombre for p in items]) for nombre, items in secciones],
            [('Vacuno', ['Asado', 'Vacío']), ('Cerdo', ['Bondiola'])],
        )

    def test_seccion_cortada_sigue_en_la_otra_columna_con_su_titulo(self):
        reparto = repartir(self.secciones(5), 4, 2)
        self.assertEqual(reparto[1][0], ('seccion', 'Sección 1', True))
        self.assertEqual(len(reparto[0]), 4)

    def test_una_seccion_no_empieza_en_el_ultimo_renglon(self):
        reparto = repartir(self.secciones(2, 2), 4, 2)
        self.assertEqual([r[0] for r in reparto[0]], ['seccion', 'producto', 'producto'])
        self.assertEqual(reparto[1][0], ('seccion', 'Sección 2', False))

    def test_si_no_entra_en_las_columnas_devuelve_none(self):
        self.assertIsNone(repartir(self.secciones(20), 5, 2))

    def test_cada_seccion_tiene_su_color(self):
        colores = _colores_por_seccion(self.secciones(*([1] * 12)))
        self.assertEqual(len(set(colores.values())), 12)

    def test_si_son_demasiados_sale_en_varias_hojas_sin_romperse(self):
        self.crear_productos(400)
        self.assertGreater(paginas_pdf(generar_lista_precios()), 1)

    def test_sin_productos_igual_genera_la_hoja(self):
        self.assertEqual(paginas_pdf(generar_lista_precios()), 1)


class ListaPreciosVistaTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre='Vacuno')
        Producto.objects.create(nombre='Asado', codigo='601', precio=Decimal('13900'), categoria=categoria)
        User.objects.create_user(username='carnicero', password='clave')

    def test_la_pantalla_ofrece_los_tres_formatos(self):
        self.client.login(username='carnicero', password='clave')
        response = self.client.get(reverse('pos:lista_precios'))
        self.assertEqual(response.status_code, 200)
        for formato in ('tabla', 'miniaturas', 'catalogo'):
            self.assertContains(response, reverse('pos:lista_precios_pdf', args=[formato]))
        self.assertContains(response, 'Asado')  # sin foto: lo avisa

    def test_cualquier_usuario_logueado_descarga_cada_formato(self):
        self.client.login(username='carnicero', password='clave')
        for formato in ('tabla', 'miniaturas', 'catalogo'):
            with self.subTest(formato=formato):
                response = self.client.get(reverse('pos:lista_precios_pdf', args=[formato]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertIn(f'attachment; filename="lista_precios_{formato}_', response['Content-Disposition'])
                self.assertTrue(response.content.startswith(b'%PDF'))

    def test_formato_desconocido_da_404(self):
        self.client.login(username='carnicero', password='clave')
        response = self.client.get(reverse('pos:lista_precios_pdf', args=['otro']))
        self.assertEqual(response.status_code, 404)

    def test_sin_login_no_descarga(self):
        self.assertEqual(self.client.get(reverse('pos:lista_precios')).status_code, 302)
        self.assertEqual(self.client.get(reverse('pos:lista_precios_pdf', args=['tabla'])).status_code, 302)


class ListaPreciosConFotosTests(TestCase):
    """Con fotos de verdad (en una carpeta temporal de media)."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajustes = override_settings(MEDIA_ROOT=self.media)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        categoria = Categoria.objects.create(nombre='Vacuno')
        for i in range(70):
            imagen = io.BytesIO()
            ImagenPIL.new('RGB', (600, 450), (150 + i, 30, 40)).save(imagen, 'JPEG')
            Producto.objects.create(
                nombre=f'Corte {i}', codigo=str(601 + i), precio=Decimal('13900'), categoria=categoria,
                foto=SimpleUploadedFile(f'corte{i}.jpg', imagen.getvalue(), content_type='image/jpeg'),
            )

    def test_tabla_con_fotitos_entra_en_una_hoja(self):
        pdf = generar_lista_precios(formato='miniaturas')
        self.assertEqual(paginas_pdf(pdf), 1)
        self.assertIn(b'/Subtype /Image', pdf)

    def test_catalogo_lleva_las_fotos_achicadas(self):
        pdf = generar_lista_precios(formato='catalogo')
        self.assertGreaterEqual(paginas_pdf(pdf), 1)
        self.assertIn(b'/Subtype /Image', pdf)
        self.assertLess(len(pdf), 70 * 40 * 1024)  # fotos achicadas, no las originales

    def test_foto_borrada_no_rompe_la_lista(self):
        producto = Producto.objects.first()
        os.remove(producto.foto.path)
        self.assertTrue(generar_lista_precios(formato='catalogo').startswith(b'%PDF'))


class ImportarProductosPorCodigoTests(TestCase):
    """El Excel del catálogo se importa por código (PLU), igual en la PC y en la nube."""

    def setUp(self):
        self.vacuno = Categoria.objects.create(nombre='Carne vacuna')
        self.congelados = Categoria.objects.create(nombre='Congelados')
        self.asado = Producto.objects.create(
            nombre='Asado', codigo='601', precio=Decimal('10000'), categoria=self.vacuno, codigo_barras='7790001',
        )
        self.nuggets = Producto.objects.create(
            nombre='Nuggets gigantes', codigo='670', precio=Decimal('12500'), categoria=self.congelados,
            unidad=Producto.UNIDAD_UNIDAD,
        )

    def importar(self, filas, dry_run=False):
        import tablib
        from .resources import ProductoResource

        datos = tablib.Dataset(headers=['codigo', 'nombre', 'categoria', 'unidad', 'precio', 'activo'])
        for fila in filas:
            datos.append(fila)
        return ProductoResource().import_data(datos, dry_run=dry_run)

    def test_actualiza_por_codigo_y_crea_los_nuevos(self):
        resultado = self.importar([
            ['601', 'Asado', 'Carne vacuna', 'kg', '13900', '1'],
            ['670', 'Nuggets gigantes', 'Congelados', 'kg', '12500', '1'],
            ['674', 'Roast beef', 'Carne vacuna', 'kg', '12900', '1'],
        ])

        self.assertFalse(resultado.has_errors())
        self.asado.refresh_from_db()
        self.nuggets.refresh_from_db()
        self.assertEqual(self.asado.precio, Decimal('13900'))
        self.assertEqual(self.asado.codigo_barras, '7790001')  # no venía en el Excel: queda igual
        self.assertEqual(self.nuggets.unidad, Producto.UNIDAD_KG)
        self.assertEqual(Producto.objects.get(codigo='674').nombre, 'Roast beef')
        self.assertEqual(Producto.objects.count(), 3)

    def test_rubro_inexistente_es_error_y_no_cambia_nada(self):
        resultado = self.importar([['601', 'Asado', 'Rubro que no existe', 'kg', '13900', '1']], dry_run=True)
        self.assertTrue(resultado.has_validation_errors() or resultado.has_errors())
        self.asado.refresh_from_db()
        self.assertEqual(self.asado.precio, Decimal('10000'))
