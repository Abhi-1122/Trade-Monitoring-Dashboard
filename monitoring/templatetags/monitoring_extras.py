from django import template
from django.urls import reverse
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def sort_header(field, label, current_sort):
    """
    Render a clickable <th> that toggles ascending/descending sort on `field`,
    re-requesting the orders table partial via HTMX with the current filter
    form's values included (so sorting doesn't reset desk/status/symbol filters).
    """
    is_active = current_sort.lstrip("-") == field
    next_sort = f"-{field}" if (is_active and not current_sort.startswith("-")) else field
    arrow = ""
    if is_active:
        arrow = " ▼" if current_sort.startswith("-") else " ▲"

    url = reverse("orders-table")
    return format_html(
        '<th class="sortable{active_class}" '
        'hx-get="{url}?sort={next_sort}" '
        'hx-include="#orders-filter-form select" '
        'hx-target="#orders-table-wrapper" '
        'hx-swap="innerHTML">{label}{arrow}</th>',
        active_class=" sort-active" if is_active else "",
        url=url,
        next_sort=next_sort,
        label=label,
        arrow=arrow,
    )
