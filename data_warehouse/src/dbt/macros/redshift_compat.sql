{# Comparación con nulos sin IS DISTINCT FROM, sin centinelas ni cast. #}
{% macro rs_distinct(left, right) -%}
(({{ left }} is null and {{ right }} is not null)
 or ({{ left }} is not null and {{ right }} is null)
 or ({{ left }} is not null and {{ right }} is not null and {{ left }} <> {{ right }}))
{%- endmacro %}
