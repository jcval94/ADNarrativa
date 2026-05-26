# Constitución de Anotación v0.1

Versiones efectivas:

- `taxonomy_version_effective`: `v0_1`
- `prompt_version_effective`: `v0_1`
- `validator_version_effective`: `v0_1`

## Propósito

Esta constitución define la semilla auditable de `narrative_dna`. No es sólo una taxonomía de etiquetas: cada función nace con fronteras, reglas de prioridad, ejemplos positivos y negativos, pares mínimos y validadores esperados. La meta es que dos frases similares reciban decisiones compatibles o, cuando diverjan, que la diferencia sea explicable.

## Principios

- JSON es la fuente de verdad.
- `final_notation` se deriva del JSON validado.
- La precisión tiene prioridad sobre cobertura falsa.
- La ambigüedad se conserva con baja confianza y `needs_review=true`.
- Una etiqueta final requiere `evidence_spans` o una regla explícita.
- Toda etiqueta confundible rechazada debe registrarse en `rejected_labels`.
- CSV sólo puede existir como export derivado.

## Notación Derivada

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Ejemplos:

```text
(P+V)_S1{0}
(K+Y)!_E2{-}
(S+I+U)_C1{+}
```

La notación nunca decide la anotación. Si cambia `functions`, `certainty`, `emotion_expressed`, `emotion_intensity` o `stance`, la notación se recompila.

## Campos Obligatorios Por Unidad

Cada unidad debe conservar funciones activas, función primaria, funciones secundarias, funciones heredadas, certeza, emoción expresada, emociones mencionadas, postura, target, acto de habla, lógica opcional, spans de evidencia, etiquetas rechazadas, flags de validación, estado de revisión, método, confianza, versiones y notación derivada.

## Funciones Narrativas

Las fichas completas viven en `annotation_guidelines/taxonomy_v0_1.json` y se reflejan en `configs/taxonomy_v0_1.json`. Los códigos v0.1 son:

| Código | Función |
| --- | --- |
| A | afirmación simple |
| K | claim fuerte |
| O | opinión/interpretación |
| F | definición |
| Y | explicación causal |
| D | dato/evidencia |
| Q | cita/voz externa |
| P | pregunta |
| R | respuesta |
| E | ejemplo |
| H | historia/anécdota |
| G | analogía/comparación |
| C | contraste/giro |
| B | objeción/refutación |
| X | advertencia/riesgo |
| T | transición |
| M | metacomentario |
| L | lista/enumeración |
| Z | cierre/conclusión |
| S | solución/recomendación |
| I | instrucción/paso operativo |
| U | utilidad/aprendizaje |
| V | llamada al espectador |
| N | no clasificado |

## Emoción, Certeza Y Postura

Emoción expresada usa códigos compactos: `N`, `A`, `L`, `C`, `S`, `E`, `M`, `T`, `D`, `F`, `I`. Emoción mencionada se guarda aparte en `emotions_mentioned`; mencionar miedo, enojo o tristeza no prueba que el hablante lo esté expresando.

Certeza:

- `none` deriva a vacío.
- `strong` deriva a `!`.
- `tentative` deriva a `~`.
- `uncertain` deriva a `?`.

Postura:

- `positive` deriva a `+`.
- `negative` deriva a `-`.
- `mixed` deriva a `±`.
- `neutral` deriva a `0`.

## Reglas Obligatorias

- `N` es exclusiva.
- `K` hereda `A`, pero `A` se guarda como `inherited_functions`.
- `D` exige evidencia concreta.
- `R` exige pregunta explícita cercana, pregunta implícita clara o estructura pregunta-respuesta.
- `Y` exige explicación causal o mecanismo.
- `E`, `H` y `G` deben separarse por caso puntual, relato con arco y analogía entre dominios.
- `S`, `I` y `U` deben separarse por recomendación, paso ejecutable y beneficio.
- `C`, `B` y `X` deben separarse por contraste, refutación y riesgo.
- `V` es ortogonal y puede coexistir con muchas funciones.
- `logic` es opcional.
- Más de cinco funciones activan `possible_overlabeling`.
- Toda etiqueta final debe tener evidencia o regla clara.
- Toda etiqueta confundible rechazada debe registrarse.

## Artefactos De Soporte

- `taxonomy_v0_1.json`: fichas completas por función, emociones, certeza, postura y relaciones.
- `label_boundaries_v0_1.json`: fronteras explícitas y reglas de decisión.
- `minimal_pairs_seed_v0_1.jsonl`: 143 pares mínimos semilla.
- `positive_negative_examples_v0_1.jsonl`: ejemplos por función.
- `validator_rules_seed_v0_1.json`: reglas esperadas, aún no implementadas.
- `decision_trees_v0_1.md`: árboles de decisión para fronteras críticas.
- `notation_contract_v0_1.md`: contrato de notación derivada.
