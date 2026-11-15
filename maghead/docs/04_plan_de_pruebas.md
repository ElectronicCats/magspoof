# 04 · Plan de pruebas y criterios de avance

Tres niveles que **no** son equivalentes y se reportan por separado (los calcula `tools/maghead/metrics.py`):

| Nivel | Definición operativa |
|---|---|
| **L1 – señal detectada** | SNR ≥ 12 dB entre la amplitud mediana de pico en el preámbulo de ceros y el ruido rms en una ventana sin tarjeta |
| **L2 – transiciones recuperadas** | 100 % de las transiciones esperadas en la región de datos, sin transiciones extra (la cuenta esperada sale de la cadena conocida de la tarjeta) |
| **L3 – pista completa correcta** | La cadena decodificada es idéntica a la grabada, con paridad de cada carácter y LRC correctos |

Una forma de onda visible en el osciloscopio es L1. Solo L3, repetido y con estadística, cuenta como "lee".

## 1. Instrumentación mínima

- Osciloscopio de 2 canales (≥ 12 bits efectivos o modo de alta resolución deseable), sondas ×1/×10.
- Frente analógico de `hw/afe/` + Raspberry Pi Pico 2 con `fw/maghead_capture`, **o** interfaz de audio USB de 96/192 kHz conectada al jack de monitor (mejor rango dinámico para estudiar la señal cruda).
- Medidor LCR (1 kHz y 10 kHz) y multímetro de 4 hilos o miliohmímetro.
- Microscopio estereoscópico con retícula o cámara calibrada; micrómetro; calibrador; galgas o cinta de Kapton de espesor conocido (12.5 / 25 / 50 µm).
- Báscula de 0.1 g para calibrar la fuerza de las lengüetas.
- Grabador/lector comercial de 3 pistas HiCo/LoCo (para escribir las tarjetas y como lector de control).
- Para velocidad controlada: un eje lineal motorizado. Opción práctica: fijar la tarjeta al carro de una impresora 3D y mover con `G1 X… F…` (velocidad conocida tras la aceleración); el banco queda fijo.
- MagSpoof V5 para la prueba de acoplamiento.

## 2. Tarjetas de laboratorio

Grabar y verificar con el lector comercial; etiquetar físicamente. Datos sintéticos, sin números reales.

| ID | Coercitividad | Contenido |
|---|---|---|
| C1 | LoCo | T1 y T2 con las cadenas de prueba de `tools/README.md` (mezcla de unos y ceros) |
| C2 | HiCo | igual que C1 |
| C3 | LoCo | T2 con el máximo de ceros (`;0000…0?`): amplitud y velocidad; T1 con longitud máxima (79 caracteres) |
| C4 | HiCo | T1 de 79 caracteres con muchos unos (peor caso de densidad) |
| C5 | la que resulte | tarjeta envejecida o rayada, solo al final |

Tres ejemplares de C1 y C2 como mínimo, para separar variación de tarjeta de variación de cabezal.

## 3. Formato de datos

Un archivo `.npz` por pasada (canales A y B, bits digitales, fs, tiempos de compuerta) y un `.json` con el esquema documentado en `tools/README.md`: tarjeta, cadena esperada, pista, variante y número de serie del sitio, entrehierro/separador, cinta, separación añadida, fuerza, desalineación lateral, azimut, ganancias, velocidad nominal y cómo se produjo, operador, fecha, versión de firmware. `tools/maghead/report.py` agrega carpetas en CSV con intervalos de Wilson al 95 %.

Estructura sugerida: `datos/<fecha>/<variante>_<serie>/<prueba>/<nnn>.npz`.

## 4. Pruebas

Cada condición: **≥ 30 pasadas** (con 30/30 aciertos el límite inferior del intervalo al 95 % es ≈ 89 %; para afirmar ≥ 97 % hacen falta ≈ 120 sin fallo). Canal B siempre conectado a la referencia disponible.

| # | Prueba | Procedimiento | Qué se obtiene |
|---|---|---|---|
| **T0** | Banco y AFE sin cabezal | Entrada en corto y con 12 Ω; ruido en cada ganancia; respuesta en frecuencia con generador y divisor 1000:1 | Ruido referido a la entrada y banda reales, contra `hw/afe/afe_analysis.md` |
| **T1** | Cupón A (pistas al aire) | Posición P2 (pista 2), tarjetas C3/C1, velocidades 0.2–1 m/s; elementos A1…A4 | Amplitud por conductor → **Mr·δ**; A1 vs A2 → pérdida por separación real; A1 vs A3 → efecto del ancho; repetir en P1 para confirmar que T1 no se resuelve |
| **T2** | Control H-0 (sin cinta) | Mismas pasadas que T3 | Captación directa de las bobinas y diafonía; nivel de zumbido ambiente; define el suelo de todo lo demás |
| **T3** | Caracterización eléctrica de cada sitio H | R, L(1 kHz, 10 kHz) antes y después de la cinta | η y reluctancia estimadas por ΔL; detecta bobinas defectuosas |
| **T4** | Cada variante H sobre **pista 2** (P2 con S1) | 30 pasadas a mano + velocidades controladas 0.05 / 0.1 / 0.25 / 0.5 / 1.0 m/s, ambos sentidos | L1/L2/L3 por velocidad; amplitud normalizada (µV·s/m); PW50; resolución unos/ceros |
| **T5** | Las variantes que pasen T4, sobre **pista 1** (P1 con S1) | Igual que T4 | Lo mismo: es la prueba que decide |
| **T6** | Sensibilidad mecánica (la mejor variante, T1) | (a) separación: 0 / 12.5 / 25 / 50 µm de Kapton sobre el polo; (b) fuerza: 0.3 / 0.7 / 1.5 N; (c) desalineación lateral: 0, ±0.25, ±0.5, ±0.75 mm; (d) azimut: girar el cupón con las ranuras M3, 0 / 1 / 2° | Curvas de amplitud y L3 contra cada variable; se compara la pendiente medida con 0.45 dB/µm |
| **T7** | Repetibilidad y desgaste | 3 unidades de la misma variante; 500 y 2000 pasadas con inspección al microscopio y re-medida de T5 | Dispersión entre unidades hechas a mano; degradación de la cinta y del borde |
| **T8** | Acoplamiento con la bobina de emulación | MagSpoof V5 a 0 / 10 / 30 mm del cupón, coplanar y apilado, emitiendo pista 2; capturar la salida del AFE y la entrada | Tensión inducida en el cabezal, tiempo de recuperación del AFE, rechazo real frente al −35/−42 dB geométrico |
| **T9** | Dos pistas simultáneas (solo si T5 pasa) | S1 en T1 y S2 en T2 a la vez, canales A y B | Diafonía entre sitios, registro lateral simultáneo, decodificación de dos canales |
| **T10** | Cabezal comercial de referencia | Un cabezal comercial con hoja de datos en el canal B, sobre una pista libre de la misma tarjeta, en el mismo banco | Verdad de referencia de tiempos de transición y velocidad instantánea; factor de amplitud real entre el híbrido y un cabezal convencional |

Sobre T10: aporta valor porque da la posición de cada transición independientemente del cabezal bajo prueba, justo cuando este todavía no decodifica. Requiere un soporte mecánico para el cabezal elegido, que no está diseñado (pendiente P-07). Mientras tanto la velocidad sale de las compuertas ópticas (media) y del eje motorizado.

## 5. Procedimiento de una serie

1. Limpiar tarjeta y polos con isopropanol; registrar temperatura y humedad.
2. Montar el cupón en P1 o P2 con pasadores; apretar M3; medir la altura de ranura con galgas en ambos extremos del cupón.
3. Ajustar y medir la fuerza de la lengüeta.
4. Elegir ganancia para que el pico mayor quede entre 30 % y 80 % de la escala; anotarla.
5. Capturar 2 s sin tarjeta (ruido) y después las pasadas. No descartar pasadas "malas": todas cuentan.
6. Ejecutar `metrics.py` y `report.py`; revisar a ojo 3 formas de onda por condición.
7. Guardar fotos del sitio antes y después de la serie.

## 6. Criterios de decisión

Los umbrales son propuestas iniciales; se fijan antes de medir y no se mueven después de ver los datos.

| Puerta | Condición | Si se cumple | Si no |
|---|---|---|---|
| **G0** | T0: ruido de entrada ≤ 1 µV rms (100 Hz–20 kHz) y banda según diseño | seguir | corregir el AFE antes de medir cabezales |
| **G1** | T1: señal del cupón A medible en pista 2 y coherente con el modelo dentro de un factor 3 | se fija Mr·δ y se recalculan las amplitudes del híbrido | revisar modelo o contacto antes de interpretar el híbrido |
| **G2** | T4: una variante H con L3 ≥ 95 % en pista 2 a 0.1–1.0 m/s, y señal ≥ 20 dB sobre H-0 | pasar a pista 1 | si hay L1 pero no L2: problema de resolución/contacto → revisar d y entrehierro. Si no hay L1: problema de eficiencia → medir ΔL, cambiar material o variante |
| **G3** | T5: L3 ≥ 90 % en pista 1 a 0.1–1.0 m/s con SNR ≥ 20 dB y relación unos/ceros ≥ 0.4 | la geometría es candidata: pasar a T6–T9 y a una rev B con más espiras y cabezal doble | con L2 intermitente: iterar entrehierro y contacto (cresta bajo el polo, cinta más delgada, preforma grabada). Con unos/ceros < 0.25 en la mejor condición de contacto: la geometría plana no alcanza → evaluar núcleo perpendicular (§5.4 de `01`) |
| **G4** | T6: ventana de funcionamiento ≥ ±0.4 mm lateral, ≥ 25 µm de separación añadida y un rango de fuerza de 2:1 | es fabricable con tolerancias de PCB | rediseñar la mecánica de contacto antes de pensar en producto |
| **G5** | T7: 3 unidades dentro de ±3 dB entre sí y sin pérdida > 3 dB tras 2000 pasadas | definir proceso de fabricación de la preforma | el ensamblaje manual no es representativo: pasar a preformas grabadas antes de concluir |

Abandono de una variante: si tras dos iteraciones de ensamblaje con medidas de entrehierro y solape dentro de objetivo no alcanza G2. Abandono de la ruta híbrida plana: si ninguna variante alcanza G3 con d medido ≤ 25 µm y η estimada por ΔL ≥ 0.2; en ese caso el límite es físico y no de ejecución.

## 7. Qué se decide con cada resultado

- Mr·δ medido (T1) → dimensiona espiras y capas de la rev B y dice si 72 espiras bastan.
- ΔL (T3) → qué material y cuántos dobleces tolera; si H-P (sin enhebrar) es viable.
- Pendiente de separación (T6a) → cuánto recubrimiento antidesgaste se puede pagar.
- T8 → distancia mínima entre bobina de emulación y cabezal, y si hace falta blindaje o solo multiplexar.
