# Auditoría Adversarial v0.1

Versiones efectivas: `taxonomy_version_effective=v0_1`, `prompt_version_effective=v0_1`, `validator_version_effective=v0_1`.

## Alcance

Esta auditoría revisa la Constitución de Anotación v0.1 antes de implementar clasificadores. Se leyeron la constitución, taxonomía, árboles de decisión, fronteras, pares mínimos y reglas esperadas. También se muestrearon transcripciones reales desde `data/transcripts/videos` para detectar patrones de ambigüedad en discurso natural.

No se modifica `taxonomy_v0_1.json` en este paso. Las propuestas quedan en `taxonomy_revision_plan_v0_2.json` para consolidación posterior.

## Hallazgos Principales

- A/K/O aún depende demasiado de fuerza retórica y requiere una prueba de disputabilidad.
- D/Q/K necesita prioridad explícita entre fuente, evidencia y conclusión.
- R/Y necesita anclaje formal para evitar respuestas fantasma.
- La función `N` y la emoción `N` deben tratarse como namespaces separados.
- La certeza debe separarse de intensidad emocional y fuerza retórica.
- V puede inflar funciones activas si no se trata como ortogonal secundaria.
- T/M/L/Z y E/H/G son los grupos más vulnerables en transcripciones largas.

## Issues

- `AUDIT-001` [critical] A, K, O: La frontera entre descripción, tesis fuerte e interpretación todavía depende demasiado de fuerza retórica.
- `AUDIT-002` [high] D, Q, K: Los enunciados con 'según' pueden ser cita, dato o claim atribuido, y la ficha no fija prioridad suficiente.
- `AUDIT-003` [high] P, R, Y: R puede activarse falsamente por una frase posterior causal sin pregunta ancla.
- `AUDIT-004` [critical] N, emotion:N: El código N existe como función no clasificada y como emoción neutral; son namespaces distintos pero visualmente confundibles.
- `AUDIT-005` [high] certainty, K, E, emotion: La certeza strong puede confundirse con énfasis emocional, insulto o tono tajante.
- `AUDIT-006` [medium] V, P, I, S: V es ortogonal y puede disparar sobre-etiquetado con preguntas o instrucciones dirigidas al espectador.
- `AUDIT-007` [high] T, M, L, Z: Intros de creadores y cierres breves mezclan transición, metacomentario, lista y conclusión.
- `AUDIT-008` [high] E, H, G: El dataset contiene relatos, ejemplos y metáforas largas; la frontera actual es correcta pero insuficiente para fragmentos mixtos.
- `AUDIT-009` [medium] S, I, U: Frases tipo 'te propongo algo simple' pueden ser recomendación, instrucción y utilidad en una sola unidad.
- `AUDIT-010` [high] C, B, X: Negación, contraste y advertencia se solapan en frases con 'pero', 'no' y 'cuidado'.
- `AUDIT-011` [high] stance, emotion: Postura y emoción pueden confundirse cuando el hablante celebra o se indigna sobre un target.
- `AUDIT-012` [medium] SUP, EXPL, CAUSE: Relaciones soporte, explicación y causa pueden solaparse antes de definir detector de relaciones.

## Acciones Para v1.0

1. Resolver todos los issues critical y high antes de consolidar v1_0.
2. Añadir pares mínimos derivados de los casos ambiguos generados.
3. Reforzar reglas de prioridad para grupos estructurales y de acción.
4. Añadir validadores para namespace de `N`, certeza epistémica, postura con target y sobre-etiquetado.
5. Mantener v0_1 como versión efectiva durante esta auditoría.
