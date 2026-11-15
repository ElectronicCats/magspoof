# Notas de PCB - maghead_afe (rev A)

Prototipo de laboratorio rev A - candidato, no liberado para fabricacion sin revision humana.
Todo se regenera y se vuelve a verificar con `sh build.sh` (necesita docker + imagen `kicad/kicad:9.0`).

## Resumen

| Dato | Valor |
|---|---|
| Placa | 90.0 x 60.0 mm, 1.6 mm, esquinas R3, 4 taladros M3 NPTH 3.2 mm a 4 mm de cada esquina |
| Capas | F.Cu senal + componentes / In1.Cu plano GND / In2.Cu plano +3V3A / B.Cu senal + relleno GND |
| Componentes | 96 del esquematico (todos en la cara F) + H1..H4 (solo placa) |
| Pistas / vias | 587 segmentos, 54 vias (38 a planos GND/+3V3A, 16 de senal) |
| Anchos | senal 0.25 mm, alimentacion (VBUS, +3V3C, enlaces y bajadas a plano) 0.40 mm |
| Reglas (.kicad_pro) | clearance 0.20, pista min 0.15, via 0.60/0.30, cobre-borde 0.30, taladro-cobre 0.25 |

## Como se genero

`gen_afe_pcb.py` (corre dentro del contenedor, usa `pcbnew`):

1. Lee `maghead_afe.net`, carga cada huella de stock de `/usr/share/kicad/footprints`, asigna
   net, funcion y tipo de pin a cada pad, la ruta al simbolo (paridad) y el atributo DNP.
2. Colocacion por coordenadas explicitas (tabla `PL`/`PL_A`). El canal B es el espejo del A
   respecto a y = 30 mm, desplazado -1.27 mm en x porque los pines del canal B de los SOIC-8
   duales quedan un paso a la izquierda de los del canal A (U1, U2 y U4 van girados 270 grados:
   fila de arriba = canal A, fila de abajo = canal B).
3. Ruteo propio: A* sobre rejilla de 0.1 mm, 2 capas (F.Cu/B.Cu) con vias, estado con direccion
   (penaliza giros, sin angulos agudos), obstaculos inflados por clearance + medio ancho + 0.02.
   Orden: nodos sensibles de etapa 1 -> realimentaciones -> locales -> alimentacion -> vias a
   plano -> nets largas (S2x, VREF, ADC, CMP, MON). No hizo falta rip-up: 0 fallos.
4. GND y +3V3A: cada pad SMD baja a su plano con una via propia (o compartida) y un tramo de
   0.4 mm; los pads THT conectan directo con alivio termico. Ademas hay enlaces en F.Cu entre el
   pin de alimentacion de cada CI y sus condensadores de desacoplo.
5. Zonas rellenadas con `ZONE_FILLER` (hay que guardar y recargar la placa antes: sobre un
   `BOARD` recien creado el relleno revienta en KiCad 9.0.9).
6. Serigrafia: rotulos fijos + referencias colocadas por busqueda de hueco libre (sin pisar
   pads, courtyards ni otros textos); las de las zonas densas tienen posicion manual (`REFPOS`).
7. Mezcla las reglas de diseno y las netclasses en `maghead_afe.kicad_pro` conservando las
   claves del esquematico (`sheets`, `schematic`, ...).

Restricciones impuestas al ruteador:

- `HEAD_x_P`, `HEAD_x_N`, `INx_P`, `FB1x`: solo F.Cu, sin vias.
- `FB2x`, `AC_x`, `G1x_J`, `CMPx_P`, `MON_x_C`: solo F.Cu.
- `CMP_A`, `CMP_B`, `CMPx_H`: prohibido x < 60 mm; `ADC_x`, `MON_x`: prohibido x < 48 mm.
- Sin pistas ni vias entre los dos pads de un 0603/0805.

## Colocacion

- Flujo de izquierda a derecha; canal A arriba, canal B abajo.
- J1/J2 en el borde izquierdo (x = 4), pin 1 = P hacia el centro de la placa.
- Etapa 1: R101/C101/R100/D101 -> R102/C102 -> U1 (24, 30), con R103/C103 justo sobre los pines
  2-1 (6-7) y R104/R105/JP101 encima.
- U3 (VREF) en el eje, entre U1 y U2. U2 en (48, 30) con la red de realimentacion en dos
  columnas sobre sus pines y JP102..JP104 en fila encima (debajo para el canal B).
- U4 (comparador) en (68, 30), a 44 mm de U1; RV101/RV201 arriba/abajo de U4.
- J4 en el borde derecho (x = 87), LDO U5 + C20/C21/C22 + TP3 arriba a la derecha, D3/C23 junto
  a J4.8, J3 en el borde inferior derecho (su huella trae el tramo de borde con la muesca).
- TP1 (GND) a la izquierda, entre los dos conectores de cabezal.

Desacoplo (centro de pad a centro de pin): 100 nF a 2.1 mm (C10-U1.8, C12-U2.8, C32-U3.8,
C41-U4.8); los de 1 uF de la misma fila quedan a 4.2 mm. U5: C20 2.5 mm, C21 2.3 mm, C22 4.5 mm.

## Longitudes de los nodos sensibles (pista, mm)

| Net | Canal A | Canal B |
|---|---|---|
| HEAD_x_P | 17.1 | 15.8 |
| HEAD_x_N | 10.0 | 10.0 |
| INx_P | 6.6 | 6.6 |
| FB1x | 8.9 | 8.9 |
| FB2x (nodo suma de la etapa 2, 10 pads) | 25.1 | 25.0 |

Distancia minima de las pistas `CMP_A`/`CMP_B` al cobre de los nodos de etapa 1: 42.9 mm
(`ADC_x` 31.8 mm, `MON_x` 36.3 mm). Lo calcula `check_pcb.py`.

## Verificacion

| Prueba | Resultado |
|---|---|
| `kicad-cli pcb drc --schematic-parity --severity-all` (KiCad 9.0.9) | 0 errores, 7 advertencias, 0 sin conectar, 0 diferencias de paridad |
| `check_pcb.py` (independiente, sin pcbnew) | 226 pads de 96 componentes: net, huella, valor y DNP iguales a `maghead_afe.net` |
| ERC tras modificar el `.kicad_pro` | 0 errores, 0 advertencias |
| Exclusiones DRC | ninguna; severidades por defecto de KiCad 9 |

Advertencias que quedan (las 7 son de J3, la huella de stock del jack):

| Tipo | Cant. | Justificacion |
|---|---|---|
| `silk_edge_clearance` | 6 | La huella `Jack_3.5mm_CUI_SJ1-3523N_Horizontal` dibuja en serigrafia el casquillo que sobresale del borde y define en Edge.Cuts su propio tramo de borde con muesca. KiCad recorta esa serigrafia en el borde; es cosmetico. |
| `lib_footprint_mismatch` | 1 | Unica diferencia introducida: se quito el atributo `exclude_from_bom` que trae la huella de stock, porque el esquematico SI lista J3 en el BOM (si se deja, sale una diferencia de paridad). La advertencia ya aparecia con la huella sin tocar. |

Severidades por defecto de KiCad que estan en "ignore" y por tanto no se informan:
`footprint_filters_mismatch` (afectaria a los jumpers JPxxx con huella de tira de pines, ver
`ERC_NOTES.md`), `footprint_type_mismatch`, `missing_courtyard`, `npth_inside_courtyard`,
`pth_inside_courtyard`.

## Compromisos y cosas NO verificadas

- `VREF` es un unico arbol ruteado de 148 mm (7 vias, F.Cu y B.Cu) que une etapa 1, U2 y U4;
  no es una estrella desde U3. Un tramo pasa por F.Cu bajo U4, junto a los pines del comparador.
  El esquematico no tiene aislamiento RC entre la VREF del comparador y la de la etapa 1; si el
  rebote del comparador se ve en la etapa 1 habra que separarlas en el esquematico (rev B).
- `HEAD_x_P` mide 16-17 mm porque el conector esta a 18 mm de U1 (la red de entrada va en
  linea entre ambos). No hay anillo de guarda ni relleno de GND en F.Cu alrededor de la etapa 1;
  el blindaje es el plano In1 bajo ella.
- El nodo suma `FB2x` mide 25 mm (cuatro ramas R||C + jumpers). No se ha estimado su
  capacidad parasita ni su efecto en la estabilidad.
- Los condensadores de 1 uF quedan a 4.2 mm del pin (objetivo ~3 mm); los de 100 nF si cumplen.
- La placa quedo de 90 mm (no menos) para que las referencias de la red de U2 quepan al lado
  de cada componente.
- Canal A y B no son identicos pista a pista (el ruteador no impone simetria): p. ej.
  `FB2A_J1` usa 2 vias y `FB2B_J1` ninguna; `MON_A` cruza toda la mitad derecha por B.Cu (41.8 mm).
- No verificado: encaje mecanico real de J3, RV101/RV201 y Keystone 5019 contra hoja de datos;
  correspondencia pin-pad de los CI contra hoja de datos (se usa la numeracion estandar SOIC-8
  doble / SOT-23-5 de los simbolos de stock); reglas concretas de un fabricante (solo las
  genericas de arriba); Gerbers no abiertos en un visor externo; sin render 3D; sin simulacion
  de ruido/diafonia; nada fabricado ni medido.
- `maghead_afe_pos.csv` solo incluye SMD de la cara F y excluye los DNP.

## Archivos

| Archivo | Contenido |
|---|---|
| `gen_afe_pcb.py` | generador (colocacion, ruteador, zonas, serigrafia, reglas) |
| `maghead_afe.kicad_pcb` | placa ruteada con zonas rellenas |
| `maghead_afe.kicad_pro` | proyecto con reglas de diseno y netclasses (Default, Power) |
| `drc.json`, `drc_summary.py` | informe DRC + resumen (falla si hay errores, no conectados o paridad) |
| `check_pcb.py` | verificacion independiente pads vs netlist, longitudes, distancias |
| `maghead_afe_{F,B,In1,In2,silk}.svg`, `maghead_afe_{F,B,silk}.png` | vistas por capa |
| `fab_maghead_afe/`, `maghead_afe_revA_gerbers.zip` | Gerber X2 (4 Cu, mascaras, pasta F, serigrafias, borde) + Excellon + mapa |
| `maghead_afe_pos.csv` | posiciones pick-and-place |
| `build.sh` | regenera y verifica todo |
