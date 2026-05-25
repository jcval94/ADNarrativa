# Arquitectura JSON-first de narrative_dna

## Propósito

`narrative_dna` convierte transcripciones de discursos en una representación estable, interpretable y auditable de ADN narrativo. El sistema no trata la notación compacta como dato primario. La fuente de verdad son documentos JSON y JSONL validados por contratos estrictos; cualquier representación compacta se compila desde esos contratos.

La arquitectura prioriza precisión sobre cobertura aparente. Cuando una clasificación sea ambigua, el sistema debe conservar la duda, bajar confianza y marcar revisión en vez de inventar certeza.

## Principio central

El contrato canónico es JSON validado por modelos Pydantic y JSON Schema.

La notación compacta:

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

es siempre un output derivado. Ejemplos:

```text
(P+V)_S1{0}
(K+Y)!_E2{-}
(S+I+U)_C1{+}
```

`final_notation` nunca debe editarse manualmente. Debe generarse por un compilador determinístico a partir de campos validados como `functions`, `certainty`, `emotion_expressed`, `emotion_intensity` y `stance`.

## Capas del sistema

El proyecto se divide en capas para evitar mezclar responsabilidades:

1. Contrato: modelos Pydantic, JSON Schemas, taxonomía, validadores y reglas de derivación.
2. Ingesta: carga de transcripciones, normalización y segmentación.
3. Candidatos: heurísticas conservadoras que proponen etiquetas sin cerrar decisiones ambiguas.
4. Inferencia: cliente OpenAI, clasificador estructurado y árbitros.
5. Auditoría: similitud entre frases, clusters, conflictos y review sets.
6. Revisión sintética: comité, agregador, árbitro final y confiabilidad.
7. Outputs derivados: reportes, secuencias compactas y CSV reconstruibles desde JSON/JSONL.

Cada cambio debe declarar su capa dominante. El Step 0 sólo define arquitectura y principios; no implementa código.

## JSONs principales

### `run_manifest.json`

Describe una ejecución completa. Debe incluir:

- `run_id`
- fecha y hora de ejecución
- configuración efectiva
- rutas de entrada y salida
- `taxonomy_version_effective`
- `prompt_version_effective`
- `validator_version_effective`
- modo de ejecución: con LLM, sin LLM, con adjudicator, sin adjudicator
- hashes o identificadores de artefactos relevantes cuando existan

### `documents.jsonl`

Un documento por línea. Representa la transcripción normalizada y sus metadatos.

Campos esperados:

- `run_id`
- `document_id`
- `source_path`
- `source_type`
- `text`
- `segments`
- `metadata`
- `normalization_flags`
- versiones efectivas

### `units.jsonl`

Unidades narrativas anotadas. Es el archivo central del MVP.

Cada unidad debe conservar:

- `run_id`
- `document_id`
- `unit_id`
- `text`
- `span`
- `functions`
- `primary_function`
- `secondary_functions`
- `inherited_functions`
- `certainty`
- `emotion_expressed`
- `emotion_intensity`
- `emotions_mentioned`
- `stance`
- `target`
- `speech_act`
- `logic`
- `evidence_spans`
- `rejected_labels`
- `validator_flags`
- `review_status`
- `final_notation`
- `taxonomy_version`
- `prompt_version`
- `validator_version`
- `taxonomy_version_effective`
- `prompt_version_effective`
- `validator_version_effective`

### `relations.jsonl`

Relaciones externas entre unidades. Las relaciones permitidas para el MVP son:

```text
ANS, SUP, EXPL, ELAB, EXMP, ANLG, CONTR, REFUT, RISK, SOLV, SEQ, SUM, CALL, CAUSE, COND
```

Cada relación debe incluir `run_id`, `relation_id`, `source_unit_id`, `target_unit_id`, `relation_type`, evidencia y confianza. Las relaciones deben ser auditables y no deben depender sólo de la notación compacta.

### `chains.jsonl`

Cadenas narrativas derivadas de unidades y relaciones. Una cadena resume patrones como problema-solución, pregunta-respuesta, riesgo-solución o claim-evidencia-explicación.

### `audit_report.json` y `audit_report.md`

Reportes de validación y consistencia. El JSON es el contrato auditable; el Markdown es una lectura humana derivada.

### Exports derivados

Los CSV sólo existen en `outputs/{run_id}/exports/` y deben reconstruirse desde JSON/JSONL:

```text
exports/units.csv
exports/relations.csv
exports/chains.csv
```

## Pipeline MVP

Flujo end-to-end previsto:

1. Crear `run_id`.
2. Resolver configuración efectiva de taxonomía, prompts y validadores.
3. Escribir `run_manifest.json`.
4. Cargar transcripciones desde `data/transcripts`.
5. Normalizar texto preservando trazabilidad al origen.
6. Segmentar en unidades narrativas candidatas.
7. Aplicar heurísticas conservadoras.
8. Clasificar unidades con JSON estructurado cuando el modo LLM esté activo.
9. Validar contratos y reglas determinísticas.
10. Derivar `final_notation` desde JSON validado.
11. Adjudicar casos críticos o ambiguos de forma conservadora.
12. Detectar relaciones externas entre unidades.
13. Detectar cadenas narrativas.
14. Auditar similitud semántica y consistencia de etiquetas.
15. Construir review sets para casos ambiguos, fronteras y conflictos.
16. Ejecutar revisión sintética cuando corresponda.
17. Calcular confiabilidad sintética.
18. Promover sólo `synthetic_gold_high_confidence` a regresión.
19. Escribir JSON/JSONL canónico.
20. Generar reportes y exports derivados.

## Contrato de unidad narrativa

Una unidad narrativa debe poder responder:

- qué función cumple en el discurso;
- cuál es su función primaria;
- qué funciones secundarias aparecen;
- qué funciones son heredadas por reglas determinísticas;
- qué grado de certeza expresa;
- qué emoción expresa, si alguna;
- qué emociones menciona sin necesariamente expresarlas;
- qué postura toma;
- cuál es el target de esa postura;
- qué acto de habla realiza;
- qué lógica argumentativa opcional contiene;
- qué spans sostienen la decisión;
- qué etiquetas fueron rechazadas y por qué;
- qué validadores se activaron;
- qué revisión necesita;
- cuál es la notación derivada.

La unidad no debe ocultar la ambigüedad. `rejected_labels`, `validator_flags` y `review_status` forman parte del contrato, no son metadatos secundarios.

## Validación determinística

Las reglas determinísticas son la primera defensa contra drift y sobre-etiquetado. Ejemplos esperados:

- `N_exclusive`: `N` no coexiste con otras funciones.
- `K_inherits_A`: `K` implica afirmación fuerte; `A` se mueve a `inherited_functions`.
- `D_requires_evidence`: datos o evidencia requieren spans concretos.
- `R_requires_anchor`: una respuesta requiere pregunta cercana o relación `ANS`.
- `emotion_mentioned_vs_expressed`: mencionar una emoción no equivale a expresarla.
- `primary_function_required`: toda unidad clasificada requiere función primaria.
- `overlabeling`: demasiadas funciones activan revisión.
- `notation_derivation`: `final_notation` coincide con el compilador.

Si una decisión puede resolverse por regla determinística, no debe enviarse al LLM.

## Auditoría de similitud e inconsistencias

El sistema debe detectar casos en los que frases semánticamente similares reciban anotaciones incompatibles. La auditoría no debe imponer equivalencia automática; debe producir evidencia para revisión.

Estrategia:

- normalizar unidades para comparación sin perder texto original;
- calcular similitud semántica entre unidades dentro de un run y, cuando exista gold, contra referencias estables;
- agrupar unidades similares por umbral configurable;
- comparar `functions`, `primary_function`, emoción, postura, certeza y notación derivada;
- distinguir diferencias justificadas por contexto de inconsistencias probables;
- escribir conflictos en JSONL auditable;
- alimentar review sets con pares similares divergentes.

Un conflicto de similitud no corrige la anotación por sí mismo. Debe marcar `needs_review=true` o crear un item de revisión con evidencia.

## Revisión sintética

La revisión sintética sustituye una revisión humana exhaustiva sólo como mecanismo auditable de mejora y triage. No produce `human_gold`.

Flujo previsto:

1. Construir review set con fronteras, pares mínimos, conflictos de similitud y casos de baja confianza.
2. Enviar cada caso a reviewers con perspectivas diversas.
3. Agregar resultados de forma conservadora.
4. Usar un adjudicator final aún más conservador.
5. Separar outputs en `synthetic_gold_high_confidence`, `synthetic_gold_medium_confidence` y `synthetic_gold_rejected`.

Sólo `synthetic_gold_high_confidence` puede usarse para pruebas de regresión. Los casos medium sirven para análisis; los rejected nunca se promueven.

## Versionado

Tres familias de versiones deben viajar con cada anotación y output importante:

- `taxonomy_version`
- `prompt_version`
- `validator_version`

Además, cada output JSON/JSONL/MD importante debe incluir las versiones efectivas:

- `taxonomy_version_effective`
- `prompt_version_effective`
- `validator_version_effective`

La diferencia entre versión declarada y versión efectiva permite auditar migraciones, overrides y ejecuciones con configuraciones heredadas.

### Taxonomía

Cada cambio de taxonomía debe actualizar:

- definiciones de etiquetas;
- fronteras entre etiquetas;
- pares mínimos;
- ejemplos positivos y negativos;
- validadores esperados;
- changelog o reglas de migración.

### Prompts

Los prompts deben ser versionados como contratos de inferencia. Cambiar un prompt puede cambiar decisiones, por lo que debe reflejarse en `prompt_version_effective` y en el manifiesto del run.

### Validadores

Los validadores deben tener versión propia. Una regla nueva que reduce ambigüedad requiere test. Cambiar una regla determinística puede invalidar outputs anteriores y debe quedar documentado.

## Límites intencionales del MVP

El MVP no incluye:

- dashboard;
- entrenamiento de modelos propios;
- uso de CSV como fuente de verdad;
- edición manual de notación compacta;
- promoción de gold sintético de confianza media;
- dependencias pesadas no justificadas;
- llamadas externas fuera de OpenAI cuando el flujo LLM esté explícitamente configurado.

## Criterio arquitectónico de éxito

El Step 0 está completo cuando el repositorio define con claridad:

- qué problema resuelve;
- qué queda dentro y fuera del MVP;
- qué JSONs son canónicos;
- cómo fluye el pipeline;
- cómo se audita consistencia;
- cómo se evita drift entre frases similares;
- cómo se versionan taxonomía, prompts y validadores;
- por qué la notación compacta es derivada y no fuente de verdad.
