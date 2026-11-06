from django import template

from gestion_de_carnicerias.admin_override import FACTORY_RESET_CONFIRMATION_PHRASE


register = template.Library()


@register.simple_tag
def factory_reset_confirmation_phrase():
    return FACTORY_RESET_CONFIRMATION_PHRASE


@register.filter
def pesos(value):
    """Formato monetario argentino: 1.234.567,89"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '0,00'
    neg = v < 0
    s = f"{abs(v):,.2f}"
    s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"-{s}" if neg else s


@register.filter
def absval(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return value