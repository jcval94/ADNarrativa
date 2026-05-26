# Constitución de Anotación v1.0

Versiones efectivas: `taxonomy_version_effective=v1_0`, `prompt_version_effective=v1_0`, `validator_version_effective=v1_0`.

## Propósito

v1.0 consolida la semilla v0.1 después de auditoría adversarial. No agrega ni elimina funciones: estabiliza fronteras, reglas de prioridad, ejemplos y pares mínimos para que la implementación posterior pueda ser conservadora y auditable.

## Cambios De Estabilidad

- A/K/O se decide por descripción, tesis disputable o perspectiva.
- D/Q/K separa fuente, evidencia y conclusión.
- R exige pregunta ancla; Y exige mecanismo causal.
- Función `N` y emoción `N` quedan separadas por namespace.
- La certeza es epistémica, no afectiva.
- E/H/G, S/I/U, C/B/X y T/M/L/Z tienen desempates explícitos.
- Postura requiere target evaluado; emoción requiere tono expresado.

## Regla JSON-first

JSON validado sigue siendo la fuente de verdad. `final_notation` se compila desde JSON y CSV sólo existe como export derivado.
