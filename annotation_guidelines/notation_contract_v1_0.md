# Contrato De Notación v1.0

Versiones efectivas: `taxonomy_version_effective=v1_0`, `prompt_version_effective=v1_0`, `validator_version_effective=v1_0`.

`final_notation` se deriva desde JSON validado:

```text
(FUNCIONES)[CERTEZA]_EMOCIÓNINTENSIDAD{POSTURA}
```

Reglas v1.0:

- Funciones heredadas no se imprimen como activas.
- Función `N` es abstención narrativa; emoción `N` es neutralidad afectiva.
- Certeza imprime ``, `!`, `~` o `?` según compromiso epistémico.
- Postura imprime `+`, `-`, `±` o `0` según evaluación hacia target.
- Si cambia el JSON, se recompila la notación.
- CSV sólo es export derivado.
