# inventario/views.py

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.models import Configuracion

from .balanza import productos_para_balanza
from .lista_precios import FORMATOS, generar_lista_precios


@login_required
@require_GET
def lista_precios(request):
    """Elegir qué lista de precios bajar: tabla, tabla con fotitos o catálogo con fotos."""
    productos, _ = productos_para_balanza()
    return render(request, 'inventario/lista_precios.html', {
        'cantidad': len(productos),
        'sin_foto': [p for p in productos if not p.foto],
        'volver': request.META.get('HTTP_REFERER') or '/pos/',
    })


@login_required
@require_GET
def lista_precios_pdf(request, formato):
    """La lista de precios de la balanza en PDF, en el formato pedido."""
    if formato not in FORMATOS:
        raise Http404
    ahora = timezone.localtime()
    pdf = generar_lista_precios(Configuracion.objects.first(), ahora, formato)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="lista_precios_{formato}_{ahora:%Y%m%d_%H%M}.pdf"'
    return response
