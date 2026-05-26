# Árboles De Decisión v1.0

Versiones efectivas: `taxonomy_version_effective=v1_0`, `prompt_version_effective=v1_0`, `validator_version_effective=v1_0`.

## DT_A_K_O

1. Si hay tesis disputable con soporte potencial, usar `K` y mover `A` a `inherited_functions`.
2. Si hay perspectiva o juicio sin pretensión de prueba, usar `O`.
3. Si sólo declara un estado, usar `A`.
4. Si no se puede decidir, bajar confianza y registrar `rejected_labels`.

## DT_P_R_Y

1. `P` abre demanda de respuesta.
2. `R` requiere pregunta ancla o relación `ANS`.
3. `Y` requiere mecanismo causal.
4. `R+Y` sólo si contesta explicando causa.

## DT_D_A_K_Q

1. `Q` marca atribución de voz o fuente.
2. `D` marca contenido verificable.
3. `K` marca conclusión disputable.
4. `A` queda para descripción sin dato ni tesis.

## DT_E_H_G

1. `E` es caso puntual.
2. `H` requiere actores, secuencia y desenlace.
3. `G` requiere mapeo entre dominios.

## DT_S_I_U

1. `S` recomienda remedio.
2. `I` ordena paso ejecutable.
3. `U` explica beneficio.
4. Si coexisten, la primaria es la intención dominante.

## DT_C_B_X

1. `C` contrasta proposiciones.
2. `B` refuta tesis o inferencia.
3. `X` advierte daño posible o condición de fallo.

## DT_T_M_L_Z

1. `T` mueve de sección.
2. `M` comenta el propio discurso.
3. `L` enumera contenido.
4. `Z` clausura o sintetiza.

## DT_EMOTION_EXPRESSED_MENTIONED

1. Emoción tematizada va en `emotions_mentioned`.
2. Tono afectivo observable va en `emotion_expressed`.
3. Pueden coexistir, pero no se sustituyen.

## DT_NEUTRAL_LIGHT_EMOTION

1. Usar emoción `N` si no hay señal afectiva observable.
2. Intensidad 1 requiere señal leve.
3. Intensidades 2 o 3 requieren evidencia fuerte.
4. Función `N` no equivale a emoción `N`.

## DT_STANCE

1. Identificar target.
2. `positive`, `negative` o `mixed` sólo si hay evaluación hacia target.
3. Emoción sin evaluación no cambia postura.

## DT_CERTAINTY_EPISTEMIC

1. `strong` requiere compromiso epistémico fuerte.
2. `tentative` requiere cautela explícita.
3. `uncertain` requiere duda abierta.
4. Intensidad emocional no modifica certeza.

## DT_RELATION_SUPPORT_CAUSE

1. `SUP` sostiene una tesis.
2. `EXPL` explica relación o mecanismo.
3. `CAUSE` declara causalidad entre eventos.
