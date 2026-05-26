# Árboles De Decisión v0.1

Versiones efectivas: `taxonomy_version_effective=v0_1`, `prompt_version_effective=v0_1`, `validator_version_effective=v0_1`.

## DT_A_K_O

1. Si la unidad formula una tesis disputable que pide soporte, usar `K`.
2. Si `K` aplica, guardar `A` como función heredada, no como función activa.
3. Si domina un juicio subjetivo marcado por perspectiva, usar `O`.
4. Si sólo declara un hecho o estado sin tesis fuerte, usar `A`.
5. Registrar en `rejected_labels` las alternativas confundibles.

## DT_P_R_Y

1. Si abre una demanda de respuesta, usar `P`.
2. Si contesta una pregunta cercana o implícita clara, usar `R`.
3. Si explica causa o mecanismo, usar `Y`.
4. Si contesta explicando causa, `R+Y` puede coexistir.
5. Sin anclaje de pregunta, no usar `R`.

## DT_D_A_K_Q

1. Si hay fuente o hablante externo, considerar `Q`.
2. Si hay cifra, medición u observación verificable, considerar `D`.
3. Si el dato sostiene una tesis explícita, puede coexistir `D+K`.
4. Si sólo declara un estado, usar `A`.
5. Si la frase concluye algo disputable, usar `K`.

## DT_E_H_G

1. Si ilustra con caso puntual y reemplazable, usar `E`.
2. Si hay actores, secuencia temporal y desenlace, usar `H`.
3. Si mapea un dominio a otro, usar `G`.
4. Un ejemplo con dato puede añadir `D`.
5. Una historia anecdótica no se convierte en dato cuantitativo.

## DT_S_I_U

1. Si propone remedio o recomendación, usar `S`.
2. Si ordena un paso ejecutable, usar `I`.
3. Si explica beneficio o aprendizaje, usar `U`.
4. `S+I+U` puede coexistir cuando una unidad recomienda, instruye y explica utilidad.
5. La función primaria debe ser la intención dominante.

## DT_C_B_X

1. Si sólo introduce oposición o giro, usar `C`.
2. Si ataca o invalida una tesis, usar `B`.
3. Si advierte daño potencial o condición de fallo, usar `X`.
4. `X` suele conectarse con `SOLV`; `B` con `REFUT`.
5. No convertir toda crítica en riesgo.

## DT_T_M_L_Z

1. Si mueve entre secciones, usar `T`.
2. Si comenta el acto discursivo, usar `M`.
3. Si enumera elementos, usar `L`.
4. Si resume o cierra, usar `Z`.
5. Si enumera pasos ejecutables, `I` puede ser primaria y `L` secundaria.

## DT_EMOTION_EXPRESSED_MENTIONED

1. Si la emoción es tema del enunciado pero no tono del hablante, guardarla en `emotions_mentioned`.
2. Si el hablante expresa emoción observable, usar `emotion_expressed`.
3. Si ambas ocurren, conservar ambas capas.
4. No inferir emoción por el tema si no hay señal expresiva.

## DT_NEUTRAL_LIGHT_EMOTION

1. Usar emoción `N` si no hay tono afectivo observable.
2. Usar intensidad `1` sólo si hay señal leve clara.
3. Usar intensidades `2` o `3` sólo con evidencia expresiva fuerte.
4. Si hay duda, preferir `N` y `needs_review=true`.

## DT_STANCE

1. Identificar el target de la evaluación.
2. Si la evaluación favorece el target, usar `positive`.
3. Si lo desfavorece, usar `negative`.
4. Si combina valoración favorable y desfavorable, usar `mixed`.
5. Si no hay evaluación clara, usar `neutral`.
