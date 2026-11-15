# BOM del primer experimento

Disponibilidad: comprobada solo mediante resultados de búsqueda (los sitios de los distribuidores no son accesibles desde la sesión). **Confirmar existencias, precio y ciclo de vida al comprar.** "Listado" = aparece una ficha del distribuidor; no garantiza inventario.

## A. Electrónica del frente analógico

Lista completa por referencia: `hw/afe/maghead_afe_bom.csv` (exportada del esquemático). Semiconductores:

| Ref | Fabricante / MPN | Función | Canal | Estado |
|---|---|---|---|---|
| U1, U2 | Analog Devices **AD8656ARZ** | op-amp doble de bajo ruido, SOIC-8 | Digi-Key 505-AD8656ARZ-ND, Mouser 584-AD8656ARZ | Listado; existencias distintas según región |
| U3 | Microchip **MCP6002-I/SN** | seguidor de VREF | Digi-Key, Mouser | No verificado en esta sesión |
| U4 | Microchip **MCP6562-E/SN** | comparador doble push-pull | Digi-Key MCP6562-E/SN-ND, RS | Listado, en producción |
| U5 | Diodes Inc. **AP2112K-3.3TRG1** | LDO 3.3 V | Digi-Key, Mouser, LCSC | Ya usado en MagSpoof V5 |
| D101, D201 | Nexperia **BAV99,215** | fijación de entrada | genérico multifuente | No verificado |
| D3 (opcional) | TI **LM4040C30IDBZR** | referencia 3.0 V para el ADC | Digi-Key, Mouser | No verificado |
| — | Raspberry Pi **Pico 2** (SC1631) | adquisición | Digi-Key, Mouser, distribuidores oficiales | No verificado en esta sesión |

Pasivos 0603/0805 (Yageo RC0603, Samsung CL10/CL21), cabeceras Würth 6130xx11121, jack CUI SJ1-3523N, trimmer Bourns 3296W-1-504LF, puntos de prueba Keystone 5019: MPN propuestos de memoria, sustituibles por equivalentes.

Alternativas de mismo encapsulado y patillaje para U1/U2 (a evaluar, no verificadas): TI LMP7732, TI OPA2365, ADI ADA4807-2.

## B. Banco (placa base)

| Ref | Fabricante / MPN | Cant. | Canal | Estado |
|---|---|---|---|---|
| U1, U2 | Everlight **ITR8307** (variante SMD de montaje inverso, p. ej. ITR8307/S17/TR8) | 2 | LCSC C63451; Digi-Key/Mouser sin confirmar | **Confirmar variante y patillaje con la hoja de datos antes de fabricar la base** |
| R1, R2 | 150 Ω 0603 1 % | 2 | genérico | — |

## C. PCBs

| Diseño | Especificación de pedido | Cant. mínima |
|---|---|---|
| `maghead_H` | 4 capas, 0.8 mm, 0.127/0.127 mm, vía 0.3/0.6, ranuras no metalizadas de 1.0 mm, ENIG, serigrafía solo cara B | 5 |
| `maghead_A` | 2 capas, 0.8 mm, pista mínima 0.10 mm, ENIG | 5 |
| `maghead_base` | 2 capas, 1.0 mm, recortes interiores fresados (canal de 1.2 mm), cualquier acabado | 5 |
| `maghead_spacer` | sin cobre, 1.0 mm | 5 |
| `maghead_afe` | 4 capas, 1.6 mm, 0.20/0.25 mm, vía 0.3/0.6, cualquier acabado | 5 |

## D. Materiales magnéticos y de entrehierro

| Material | Fabricante / referencia | Canal | Estado |
|---|---|---|---|
| Lámina MuMETAL recocida 0.002" (50 µm), 8" × 12" | Magnetic Shield Corp. **MU002-8** | Digi-Key | Listado |
| Cinta amorfa Co, 18 µm | Metglas **2714A** | Fabricante (metglas@metglas.com) | Sin canal de cantidad pequeña verificado; pedir muestra |
| Película de poliimida sin adhesivo 12.5 y 25 µm | DuPont Kapton HN (p. ej. CAPLINQ PIT0.5N) | CAPLINQ, distribuidores de película | Listado 12.5 µm |
| Alternativa de separador metálico | lámina de titanio 12.7 µm (Thermo Scientific 43476) o latón 25 µm | Fisher, McMaster | Listado |
| Adhesivo | cianoacrilato de baja viscosidad o epoxi de curado lento | genérico | — |
| Cinta de deslizamiento / pad | UHMW-PE o PTFE adhesiva | genérico | Espesor a medir |

## E. Mecánica

Tornillos M3 × 8 con arandela y tuerca (5), separadores hexagonales M3 de ≥ 5 mm (4), pasadores de acero Ø2.0 × 6 mm (2), cable trenzado fino para los cabezales.

## F. Referencia comercial (prueba T10, opcional)

Un cabezal con hoja de datos pública, p. ej. Techreco TG142 (28 mH, 140 Ω, 19 mVpp a 210 bpi y 7.5 ips, entrehierro 30 µm). Canal de compra en México sin verificar; no se encontró ningún cabezal desnudo en distribuidores generalistas.
