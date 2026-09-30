from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """Mantém a query string atual, sobrescrevendo/adicionando parâmetros.

    Uso no template: {% querystring page=2 %}
    """
    from django.http import QueryDict

    request = context.get('request')
    if request is None:
        return ""
    qs = QueryDict(request.META.get("QUERY_STRING", ""), mutable=True)
    for chave, valor in kwargs.items():
        if valor is None:
            qs.pop(chave, None)
        else:
            qs[chave] = str(valor)
    retorno = qs.urlencode()
    return f"?{retorno}" if retorno else ""
