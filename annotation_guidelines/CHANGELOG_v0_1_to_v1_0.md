# CHANGELOG v0.1 -> v1.0

Versiones efectivas: `taxonomy_version_effective=v1_0`, `prompt_version_effective=v1_0`, `validator_version_effective=v1_0`.

## Migración Aplicada
- `v0_1` -> `v1_0`: Consolidar definiciones tras auditoría adversarial; resolver issues críticos y altos; endurecer fronteras; convertir pares semilla validados en fixtures de regresión.
- `v0_1` -> `v1_0`: Aplicar hallazgos de auditoría adversarial v0.1 antes de consolidar v1_0.

## Issues Resueltos
- `AUDIT-001` [critical]: A/K/O se resuelve con prueba de disputabilidad: K requiere tesis defendible; O requiere perspectiva; A sólo declara.
- `AUDIT-002` [high]: D/Q/K se separa en capas: Q atribuye fuente, D contiene evidencia verificable, K formula conclusión disputable.
- `AUDIT-003` [high]: R sólo aplica con pregunta ancla o ANS; una causa sin pregunta queda como Y.
- `AUDIT-004` [critical]: Función N y emoción N quedan documentadas como namespaces distintos.
- `AUDIT-005` [high]: Certeza queda definida como compromiso epistémico, no intensidad afectiva.
- `AUDIT-007` [high]: T/M/L/Z se separan por movimiento, comentario discursivo, enumeración y cierre.
- `AUDIT-008` [high]: E/H/G se separan por caso puntual, arco temporal y mapeo entre dominios.
- `AUDIT-010` [high]: C/B/X se separan por oposición, refutación de tesis y daño potencial.
- `AUDIT-011` [high]: Postura requiere evaluación hacia target; emoción requiere tono afectivo observable.

## Decisiones
- No se agregan etiquetas nuevas.
- No se eliminan etiquetas.
- Se refuerzan validadores esperados y pares mínimos.
- v1.0 queda lista para implementación de validadores determinísticos.
