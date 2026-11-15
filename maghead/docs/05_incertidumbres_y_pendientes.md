# 05 · Incertidumbres, parámetros pendientes y estado de fabricación

## 1. Parámetros que no se conocen y cómo se miden

| # | Parámetro | Efecto en la decisión | Cómo se obtiene |
|---|---|---|---|
| U-01 | Flujo remanente de la banda (Mr·δ), LoCo y HiCo | Escala toda la señal (×3 de incertidumbre hoy). Decide espiras y capas de la rev B | Prueba T1 con el cupón A (geometría conocida, sin núcleo) |
| U-02 | Separación efectiva banda–polo conseguible con superficie plana y tarjeta flexible | Domina la resolución en pista 1 (0.45 dB/µm). Es el riesgo principal | T6a (pendiente de amplitud contra separación añadida, extrapolada a cero) y PW50 medido |
| U-03 | Permeabilidad efectiva de la cinta tras cortar, doblar y pegar | Eficiencia entre 0.1 y 0.9 | T3: incremento de inductancia con la cinta |
| U-04 | Ancho y rectitud reales del entrehierro por cada método | Resolución y repetibilidad | Microscopio en cada unidad; correlación con T5 |
| U-05 | Parámetro de transición y espesor de la capa magnética | Forma del pulso; el modelo usa a = 8 µm, δ = 10 µm supuestos | Ajuste del pulso aislado medido con el mejor contacto |
| U-06 | Rigidez real de la lengüeta de FR4 y fuerza óptima | Contacto y desgaste | Báscula; T6b |
| U-07 | Acoplamiento real bobina de emulación → cabezal | Distancia mínima y arquitectura del producto | T8 |
| U-08 | Desgaste de una lámina de 18–50 µm y del recubrimiento | Vida útil | T7 |
| U-09 | Ruido y banda reales del AFE; ENOB del ADC del Pico 2 | Margen de SNR | T0 |
| U-10 | Profundidad del elemento y longitud sensible en ALT025 / CT100 | Si alguna vez merece un cupón MR | Pregunta al fabricante: "distancia del elemento sensible a la cara superior del encapsulado y dimensión del elemento a lo largo del eje sensible" |
| U-11 | Clasificación arancelaria y normas en México para cabezal, sensores y lámina | Argumento de suministro | Agente aduanal |
| U-12 | Libertad de operación (bobinas en PCB con material blando para tarjetas) | Producto | Búsqueda de patentes dirigida |

## 2. Estado de cada entregable

| Entregable | Estado | Verificado | No verificado |
|---|---|---|---|
| Modelo físico `calc/` | Ejecutado | Solver contra Karlqvist (1.5 %); coherencia de orden de magnitud con el TG142 | Parámetros del medio; efectos 3D; µr |
| Cupón H | Diseño completo; DRC KiCad 9: 0 errores; comprobación propia entre espiras: 0 violaciones; Gerbers y taladros exportados | Conectividad, separaciones, ranuras en el archivo de taladros, vías cubiertas | Revisión humana; capacidades del fabricante elegido |
| Cupón A | Igual | Aperturas de máscara presentes; vías cubiertas | Ídem |
| Base y separador | Igual | 0 errores, 0 sin conectar | Huella y patillaje del ITR8307 inverso; rigidez |
| Esquemático AFE | ERC 0/0; netlist verificada | Conexiones según especificación | Sin PCB; MPN de pasivos; estabilidad; hardware |
| Firmware y scripts | Ver `fw/README.md` y `tools/README.md` | Lo que indiquen sus pruebas en PC | Compilación para el Pico, temporización real del ADC, caudal USB |

## 3. Advertencias de DRC aceptadas

| Tipo | Dónde | Motivo |
|---|---|---|
| `lib_footprint_issues` | todas | Las huellas (pads de cable, taladros, ranuras, ITR8307) están embebidas por el generador; no hay biblioteca "maghead" |
| `track_dangling` (4) | cupón H, F.Cu | Marcas flotantes de la línea del entrehierro, intencionadas |
| `silk_over_copper`, `silk_edge_clearance` | cupones y base | Serigrafía recortada por pads o taladros; cosmético |

El DRC se corrió con las reglas por defecto del proyecto de KiCad; las separaciones entre espiras (misma red) se validan aparte en `gen_pcbs.py`. Antes de ordenar hay que cargar las reglas del fabricante.

## 4. Lista de comprobación antes de ordenar (los Gerbers actuales son candidatos rev A, no liberados)

- [ ] P-01 Abrir las cuatro tarjetas en KiCad y revisarlas visualmente (capas internas del cupón H, cara F libre bajo los polos).
- [ ] P-02 Confirmar con el fabricante: ranura no metalizada de 1.0 × 3.0 mm, canal interior de 1.2 mm en la base, 0.127/0.127 mm en 4 capas de 0.8 mm, 0.10 mm en 2 capas, vías 0.3/0.6 cubiertas, ENIG.
- [ ] P-03 Verificar el ITR8307: variante de montaje inverso, dimensiones del recorte y patillaje (1 = cátodo, 2 = ánodo, 3 = colector, 4 = emisor según el símbolo de KiCad) contra la hoja de datos de Everlight. Si hay duda, fabricar la base sin poblar las compuertas: el resto del banco no depende de ellas.
- [ ] P-04 Decidir el ajuste de los pasadores (taladro de 2.0 en base y separador, 2.1 en cupones) según la tolerancia del fabricante.
- [ ] P-05 Tener el material magnético y el Kapton en mano, o al menos confirmado, antes de pedir las PCBs: sin ellos el cupón H no se puede ensamblar.
- [ ] P-06 Diseñar la PCB del AFE (pendiente; ver `03` §2) o montar el esquemático en una placa de prototipos con plano de masa para T0.
- [ ] P-07 Elegir el cabezal comercial de referencia y diseñar su soporte (prueba T10).
- [ ] P-08 Definir el pad de presión (material y espesor medidos).
- [ ] P-09 Confirmar que la tienda y la documentación oficial del MagSpoof V5 no contradicen lo leído en el repositorio (la página de la tienda no fue accesible).

## 5. Lo que este trabajo no demuestra

- Que el cabezal híbrido lea una tarjeta: no se ha construido nada.
- Que sea más barato, más delgado en el producto final o más fácil de suministrar que un cabezal comercial.
- Que el ensamblaje manual sea representativo de un proceso de producción.
