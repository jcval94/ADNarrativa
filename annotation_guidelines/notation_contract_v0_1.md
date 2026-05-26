# Contrato De Notación v0.1

Versiones efectivas: `taxonomy_version_effective=v0_1`, `prompt_version_effective=v0_1`, `validator_version_effective=v0_1`.

## Regla Central

`final_notation` se deriva del JSON validado. Nadie debe editarla manualmente.

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Ejemplos:

```text
(P+V)_S1{0}
(K+Y)!_E2{-}
(S+I+U)_C1{+}
```

## Fuente De Verdad

La fuente de verdad está en campos JSON:

- `functions`
- `primary_function`
- `secondary_functions`
- `inherited_functions`
- `certainty`
- `emotion_expressed`
- `emotion_intensity`
- `stance`
- `validator_flags`
- `review_status`

La notación compacta sólo resume esos campos. Si cambia el JSON, se recompila la notación.

## Compilación Esperada

- `functions` se ordena por función primaria seguida de secundarias.
- `inherited_functions` no se imprime como función activa.
- `certainty=none` no imprime símbolo.
- `strong`, `tentative` y `uncertain` imprimen `!`, `~` y `?`.
- emoción e intensidad se imprimen después de `_`.
- postura se imprime entre `{}` como `+`, `-`, `±` o `0`.

## Prohibiciones

- No editar `final_notation` a mano.
- No usar CSV como fuente de verdad.
- No inferir JSON desde notación compacta si el JSON validado está disponible.
- No promover una notación si hay flags `error` sin resolver.

CSV sólo es export derivado y debe poder reconstruirse desde JSON/JSONL.
