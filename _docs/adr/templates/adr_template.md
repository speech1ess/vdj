# ADR {{ number }}: {{ title }}

## Контекст
{{ context }}

## Решение
{{ decision }}

## Альтернативы
{% for alt in alternatives %}
- **{{ alt.name }}** — {{ alt.reason }}
{% endfor %}

## Последствия
{% for consequence in consequences %}
- {{ consequence }}
{% endfor %}

## Статус
**{{ status }}**
