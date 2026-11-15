# maghead-afe: design spec

Estado: **BORRADOR, sin bloquear.** Según el flujo `hardware-design-flow`, no se dibuja nada hasta que el
diseñador diga "locked". Cada dato de hardware está comprobado o marcado UNVERIFIED.

Sustituye a `../afe/` (rev A hecha fuera del flujo de la casa; ver "Por qué se rehace").

## Purpose and constraints
- **Qué hace:** frente analógico de laboratorio, 2 canales, para cabezales lectores de banda magnética
  experimentales (cupón H, cupón A) y un cabezal comercial de referencia. Amplifica 2 µV–20 mV, 16 Hz–30 kHz,
  y entrega cada canal a un ADC, a un comparador con histéresis y a una salida de monitor.
- **Usuarios:** ingeniería de Electronic Cats, en banco. No es producto.
- **Mecánica:** sin gabinete. Placa propuesta ≤ 60 × 40 mm, 4 × M3. Entradas de cabezal en el borde izquierdo,
  conexión al MCU y monitor en el borde derecho. Altura libre.
- **Alimentación:** 5 V (VBUS del Pico) → LDO 3.3 V analógico; consumo < 30 mA. Sin alta tensión.
- **Ensamblaje:** JLC Economic, una cara. Cantidad: **POR CONFIRMAR** (propuesta: 5).
- **Placa:** 2 capas JLC2L-1.6 con GND en ambas caras (regla de la casa; 38 de 43 placas EC son de 2 capas).
  4 capas solo si el diseñador lo pide.
- **Reglas:** `pcb-house-rules` sin excepciones: pista 0.2 señal / 0.5 potencia, vías 0.6/0.3 y 0.8/0.4,
  separación 0.2, borde 0.5, ortogonal con 45° cortos, pasivos 0603, serigrafía 1.0 mm.

## Blocks
Los números LCSC# no están asignados: salen de `jlc-bom-cost` a la cantidad real. Ninguno se inventa aquí.

| Block | Parts (LCSC#, tier) | Notes |
|---|---|---|
| Entrada ×2 | Conector de cabezal, fijación BAV99 antiparalelo, 47 Ω serie, R/C de amortiguamiento (DNP) | Un extremo de la bobina a VREF. Conector: **POR CONFIRMAR** (propuesta: JST-SH 2 pines SMD + pads de prueba) |
| Etapa 1 ×2 | ½ AD8656ARZ (LCSC# UNVERIFIED), no inversora ×11 / ×102 | 2.7 nV/√Hz según hoja de datos: UNVERIFIED en esta sesión. Selección de ganancia: **POR CONFIRMAR** (hoy puente de 2.54 THT; propuesta: puente de soldadura o DIP switch SMD) |
| Etapa 2 ×2 | ½ AD8656ARZ, inversora, ×200 / ×40 / ×9.5 / ×2 | Paso alto 16 Hz, polo ≈ 40 kHz |
| VREF | MCP6002 (LCSC# UNVERIFIED), 1.65 V | Árbol en estrella: etapa 1, etapa 2, comparador |
| Comparador ×2 | MCP6562 (LCSC# UNVERIFIED), histéresis ajustable | Trimmer: **POR CONFIRMAR** (hoy Bourns 3296 THT; propuesta: trimmer SMD o resistencia fija + pads) |
| Salidas | ADC_A/B, CMP_A/B, AREF a cabecera 1×8; monitor estéreo | Monitor: **POR CONFIRMAR** (hoy jack 3.5 mm THT; propuesta: quitarlo y dejar puntos de prueba, o conservarlo) |
| Alimentación | AP2112K-3.3 (el del MagSpoof V5; LCSC C47773 según BOM del V5), LM4040-3.0 opcional | |

## Pin budget (MCU)
El MCU no va en esta placa. Cabecera J4 hacia un Raspberry Pi Pico 2:

| Pin J4 | Net | Pico |
|---|---|---|
| 1 | VBUS | VBUS (40) |
| 2, 4 | GND | GND / AGND |
| 3 | ADC_A | GP26 / ADC0 |
| 5 | ADC_B | GP27 / ADC1 |
| 6 | CMP_A | GP2 |
| 7 | CMP_B | GP3 |
| 8 | ADC_VREF | ADC_VREF (35) |

Alternativa **POR CONFIRMAR**: montar el Pico directamente en la placa (zócalo 2×20) y eliminar J4.

## Por qué se rehace
Auditoría de `../afe/maghead_afe.kicad_pcb` con `check_routing.py` (reglas de la casa): más de 260 segmentos en
ángulo arbitrario, 9 esquinas agudas (trampas de ácido), 6 tramos largos a 45° (hasta 20 mm), pistas de 0.25 mm
fuera de la lista de la casa, borde a 0.3 mm en vez de 0.5, serigrafía de 0.8 mm, sin vertido de GND en F.Cu, 4 capas
sin necesidad, componentes THT evitables, piezas sin `LCSC#`. Además se saltó el flujo: se ruteó sin aprobar
colocación y se exportaron Gerbers sin puerta de liberación.

## Preguntas abiertas para bloquear
1. Cantidad a fabricar y si la ensambla JLC (Economic) o se suelda a mano.
2. 2 capas (propuesta) o 4.
3. Conector de entrada de cabezal.
4. Selección de ganancia: puentes THT, puentes de soldadura o DIP switch SMD.
5. Trimmer de histéresis: THT, SMD o fijo.
6. Jack de monitor: se queda o se quita.
7. Pico en zócalo sobre la placa o por cable a J4.
8. Tamaño máximo y si hay algún borde obligado para los conectores.

## Decisions (dated)
- 2026-11-15: la rev A de `../afe/` queda obsoleta; no fabricar.
- 2026-11-15: el esquema eléctrico de la rev A (netlist verificada, ERC 0/0) se conserva como punto de partida;
  cambian encapsulados, conectores y campos `LCSC#` / `manf#`.
