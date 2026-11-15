# Notas de ERC - maghead_afe (rev A)

Prototipo de laboratorio rev A - no liberado para fabricacion.

## Resultado

Comando (KiCad 9.0.9 via docker, ver `run_kicad.sh` / `build.sh`):

    kicad-cli sch erc --severity-all --format json -o erc.json maghead_afe.kicad_sch

Resultado final (`erc.json`, resumido con `erc_summary.py`):

| Severidad | Cantidad |
|---|---|
| error | 0 |
| warning | 0 |
| exclusiones / reglas desactivadas | ninguna (matriz y severidades por defecto de KiCad 9) |

No quedan advertencias que justificar.

## Condiciones en las que se obtuvo

- La imagen `kicad/kicad:9.0` arranca sin configuracion de usuario. `run_kicad.sh`
  copia las tablas globales de stock (`/usr/share/kicad/template/sym-lib-table` y
  `fp-lib-table`) a `~/.config/kicad/9.0/` antes de llamar a `kicad-cli`.
  **Sin ese paso** el ERC da 135 advertencias `lib_symbol_issues`
  ("The current configuration does not include the symbol library ...", una por
  simbolo): son un artefacto del entorno, no del esquematico. Con las tablas
  instaladas el ERC si compara cada simbolo embebido con la libreria de stock y
  no informa diferencias.
- No hay seccion `erc` en `maghead_afe.kicad_pro`: se usan las severidades por defecto.

## Decisiones tomadas para que el ERC quede limpio (y por que son legitimas)

| Punto | Que se hizo | Justificacion |
|---|---|---|
| VBUS | `PWR_FLAG` junto a U5 | VBUS entra por J4 (pin pasivo); sin la bandera U5.VIN quedaria "power pin not driven". |
| GND | `PWR_FLAG` junto a TP1 | GND tambien entra solo por J4 (pasivo). |
| +3V3C | `PWR_FLAG` tras R40 | U4.V+ se alimenta a traves de R40 (pasivo) desde +3V3A. |
| +3V3A | sin bandera | Lo excita U5.VOUT (power output). Se usa el simbolo de stock `power:+3.3VA` con el campo Value = `+3V3A` (el nombre de net lo da el Value). |
| VREF | etiquetas locales, no simbolo de alimentacion | VREF la excita la salida de U3A (pin tipo output). Un simbolo power + PWR_FLAG crearia conflicto output / power-output. |
| U3B (sin uso) | seguidor de VREF, salida con etiqueta `U3B_NC` | Entradas definidas y salida sin cargar; la net tiene 2 pines (pin 6 y 7), por eso no necesita marca de no-conexion. |
| U5 pin 4 (NC), D3 pin 3 (NC) | sin conectar | Son pines tipo `no_connect` ocultos del simbolo de stock; en el netlist salen como `unconnected-(...)`. |
| Jumpers JPxxx | simbolo `Jumper:Jumper_2_Open` con huella `PinHeader_1x02_P2.54mm_Vertical` | La huella no coincide con el filtro de huellas del simbolo (`Jumper* TestPoint*2Pads*`), pero KiCad 9.0.9 no lo senala en ERC. Es intencionado: jumper de tira de pines 2.54. |
| Nodo R115-RV101 | etiqueta `CMPA_H` / `CMPB_H` | Net interna sin nombre en la especificacion; se nombra para poder verificarla en `check_netlist.py`. |

## Lo que el ERC NO comprueba (verificado aparte o pendiente)

- Conectividad contra la intencion de diseno: `check_netlist.py` compara el netlist
  exportado con una tabla escrita a mano (44 nets, 224 pines). Resultado: OK.
- Valores, tolerancias, estabilidad, ruido: ver `afe_analysis.py` (solo modelo).
- Correspondencia pin-pad de las huellas: solo se comprobo que los nombres de pad de
  las huellas de stock existen (1..8, S/T/R del jack). No hay PCB todavia.
- Los MPN son propuestas sin contrastar con distribuidor ni hoja de datos.
