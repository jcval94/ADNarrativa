# Project Charter: narrative_dna

## Problema

Las transcripciones de discursos suelen analizarse con etiquetas inconsistentes, prompts cambiantes o resúmenes que no dejan una ruta clara de auditoría. Dos frases muy parecidas pueden recibir etiquetas distintas sin explicación, y una notación compacta puede parecer precisa aunque esconda incertidumbre, evidencia débil o decisiones incompatibles.

`narrative_dna` nace para convertir transcripciones en una representación de ADN narrativo que sea:

- estable entre ejecuciones comparables;
- interpretable por humanos;
- auditable desde evidencia textual;
- estricta en sus contratos JSON;
- conservadora ante ambigüedad;
- útil para detectar inconsistencias entre frases similares.

## Objetivo

Construir un MVP Python llamado `narrative_dna` que procese transcripciones y produzca JSON/JSONL validados por schema como fuente de verdad.

La notación compacta:

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

debe compilarse desde JSON validado, nunca editarse como dato primario.

## Principios no negociables

- JSON es la fuente de verdad.
- La notación compacta es un derivado.
- La precisión tiene prioridad sobre cobertura falsa.
- La ambigüedad debe preservarse con confianza baja y revisión explícita.
- Las decisiones determinísticas no se delegan al LLM.
- El agregador y el adjudicator final son conservadores.
- La revisión sintética no se presenta como gold humano.
- Sólo `synthetic_gold_high_confidence` puede usarse para regresión.
- CSV sólo existe como export derivado y reconstruible.
- Todo output importante debe ser trazable por `run_id` y versiones efectivas.

## Alcance MVP

El MVP cubre:

- definición de contratos JSON y JSON Schema;
- taxonomía versionada de funciones narrativas;
- guías de anotación con fronteras y pares mínimos;
- loader, normalizador y segmentador de transcripciones;
- extracción conservadora de candidatos;
- clasificación estructurada opcional con OpenAI;
- validadores determinísticos;
- compilador de notación compacta;
- adjudicación conservadora de casos críticos;
- detección auditable de relaciones externas;
- detección de cadenas narrativas;
- auditoría por similitud semántica;
- construcción de review sets;
- revisión sintética con comité;
- scoring de confiabilidad sintética;
- evaluación y regresión con gold permitido;
- outputs JSON/JSONL y exports derivados.

## No-alcance inicial

Queda fuera del MVP:

- dashboards o interfaces visuales;
- entrenamiento o fine-tuning de modelos;
- edición manual de `final_notation`;
- CSV como input canónico o fuente de verdad;
- gold humano simulado a partir de revisión sintética;
- sistemas multiusuario;
- almacenamiento en base de datos;
- streaming en tiempo real;
- optimización de gran escala antes de estabilizar contratos;
- dependencias pesadas sin justificación explícita.

## Usuarios previstos

Usuarios principales:

- investigadores de discurso que necesitan trazabilidad;
- analistas narrativos que comparan patrones entre discursos;
- equipos que requieren regresión y consistencia entre versiones;
- anotadores o revisores que necesitan fronteras claras.

El sistema debe favorecer inspección y auditoría por encima de una experiencia visual temprana.

## Artefactos canónicos

Los artefactos canónicos viven en `outputs/{run_id}/`:

```text
run_manifest.json
documents.jsonl
units.jsonl
relations.jsonl
chains.jsonl
audit_report.json
audit_report.md
dna_sequences.txt
exports/units.csv
exports/relations.csv
exports/chains.csv
```

La jerarquía de autoridad es:

1. JSON/JSONL validado.
2. Reportes JSON derivados.
3. Markdown de lectura humana.
4. Secuencias compactas derivadas.
5. CSV derivados.

Si un CSV contradice el JSON, el CSV está mal.

## Contrato mínimo por unidad

Cada unidad narrativa debe incluir:

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

También debe conservar:

- `taxonomy_version`
- `prompt_version`
- `validator_version`
- `taxonomy_version_effective`
- `prompt_version_effective`
- `validator_version_effective`

## Relaciones externas

El MVP reconoce estas relaciones entre unidades:

```text
ANS, SUP, EXPL, ELAB, EXMP, ANLG, CONTR, REFUT, RISK, SOLV, SEQ, SUM, CALL, CAUSE, COND
```

Las relaciones deben apuntar a unidades por ID y conservar evidencia. No deben inferirse sólo porque dos notaciones compactas parezcan compatibles.

## Estrategia de auditoría

La auditoría se diseña como parte del sistema, no como una fase decorativa.

Debe responder:

- qué regla produjo o corrigió una etiqueta;
- qué evidencia textual sostiene una función;
- qué etiquetas fueron rechazadas;
- qué validadores se activaron;
- qué unidades necesitan revisión;
- qué frases similares fueron anotadas de forma divergente;
- qué versión de taxonomía, prompt y validador estaba activa;
- qué outputs pueden usarse para regresión.

La salida auditable debe poder reconstruir por qué una unidad terminó con una anotación y no con otra.

## Prevención de inconsistencias entre frases similares

El proyecto tratará la similitud como un control de calidad de primera clase.

Mecanismos previstos:

- pares mínimos en la constitución de anotación;
- ejemplos positivos y negativos por etiqueta;
- grupos de confusión para funciones cercanas;
- validadores determinísticos para casos repetibles;
- auditoría semántica de unidades similares;
- review sets con conflictos de similitud;
- regresión sobre `synthetic_gold_high_confidence`;
- reportes de drift cuando cambien taxonomía, prompts o validadores.

La similitud no fuerza etiquetas iguales. El objetivo es exigir explicación cuando dos frases parecidas reciben decisiones distintas.

## Política de LLM

OpenAI puede usarse para clasificación y revisión sólo a través del cliente definido por el proyecto. Las salidas LLM deben ser estructuradas, validadas y trazables.

Reglas:

- baja temperatura para clasificación ordinaria;
- alta temperatura sólo para diversidad de reviewers sintéticos;
- agregación conservadora;
- adjudicación final todavía más conservadora;
- cache por entrada/configuración cuando aplique;
- errores o dudas deben terminar en revisión, no en certeza fabricada.

## Versionado

El proyecto versiona tres dimensiones:

- taxonomía: etiquetas, definiciones, fronteras y pares mínimos;
- prompts: instrucciones que pueden alterar decisiones;
- validadores: reglas determinísticas que transforman o rechazan anotaciones.

Cada run debe registrar las versiones efectivas en `run_manifest.json`. Cada anotación debe conservar versiones locales para permitir comparación, migración y depuración.

## Criterios de aceptación del MVP

El MVP será aceptable cuando pueda:

- leer transcripciones desde `data/transcripts`;
- producir outputs en `outputs/{run_id}`;
- validar JSON/JSONL con schemas estrictos;
- compilar notación desde JSON sin edición manual;
- marcar ambigüedad con `needs_review`;
- detectar conflictos entre frases similares;
- generar review sets auditables;
- separar synthetic gold por nivel de confianza;
- evaluar regresión sólo contra gold permitido;
- exportar CSV derivados y reconstruibles.

## Riesgos principales

- sobre-etiquetado por querer cubrir demasiado;
- prompts que cambian decisiones sin versionado;
- usar notación compacta como si fuera fuente primaria;
- confundir emoción mencionada con emoción expresada;
- promover revisión sintética como gold humano;
- aceptar inconsistencias entre frases similares sin revisión;
- introducir dependencias o interfaces antes de estabilizar contratos.

## Decisión de arranque

El primer paso del proyecto es documentar arquitectura, principios y límites antes de escribir código. El siguiente paso será scaffold del paquete Python y estructura de carpetas esperada.
