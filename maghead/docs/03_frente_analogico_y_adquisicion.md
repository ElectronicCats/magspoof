# 03 · Frente analógico de prueba y adquisición

Archivos: `hw/afe/maghead_afe.kicad_sch` (KiCad 9), `maghead_afe.pdf`, `maghead_afe.net`, `maghead_afe_bom.csv`, `afe_analysis.md`, `ERC_NOTES.md`. Regenerar y verificar: `sh hw/afe/build.sh`.

**Estado: esquemático de prototipo, ERC 0 errores / 0 advertencias, netlist comprobada contra una tabla independiente (96 componentes, 44 redes, 224 pines). No hay PCB del AFE todavía y nada se ha medido en hardware.**

## 1. Arquitectura (2 canales idénticos, alimentación única)

```
cabezal ──┬─ BAV99 antiparalelo a VREF ── 47 Ω ──(+) U1 ½AD8656  G = ×11 / ×102 (JP101)
 (N a VREF)                                         │ polo 159 kHz
                                        10 µF + 1 kΩ (paso alto 16 Hz)
                                                    │
                                        U2 ½AD8656 inversor  G = ×200 fijo; JP102/103/104 añaden ramas → ×40 / ×9.5 / ×2
                                                    │ polo ≈ 40 kHz en cada ajuste
                    ┌───────────────┬───────────────┼──────────────────┐
              1 kΩ + 2.2 nF      10 µF + 100 Ω    10 kΩ → MCP6562      TP
              → ADC (GP26/27)    → jack 3.5 mm    histéresis ±30…±350 mV → GPIO
```

| Requisito | Solución | Justificación |
|---|---|---|
| Entrada y polarización | Un extremo de la bobina a VREF (1.65 V, divisor + seguidor MCP6002); el otro a la entrada no inversora | La fuente es de ~12 Ω y flotante: no hace falta entrada diferencial; el ruido de VREF entra con ganancia 1, no ×102 |
| Ruido | AD8656 (CMOS, 2.7 nV/√Hz según su hoja de datos **[NV en esta sesión]**), red de ganancia de 10 Ω equivalentes | Modelo: 0.46 µV rms referidos a la entrada en 100 Hz–20 kHz; el amplificador aporta ~70–90 % de la potencia de ruido. La bobina sola daría 0.07 µV: hay ~17 dB de mejora posible con un amplificador bipolar de ~1 nV/√Hz, que exige alimentación de 5 V o mayor y más cuidado de estabilidad. No se adopta hasta saber si hace falta (puerta G0/G2) |
| Ganancia configurable | Etapa 1 ×11/×102; etapa 2 ×200, ×40, ×9.5, ×2 (un puente a la vez). Total ×18 a ×20 400 (25–86 dB) | Cubre cabezal comercial (decenas de mV), híbrido (10 µV–2 mV) y pistas al aire (µV). Puentes en lugar de PGA: sin conmutación ni firmware en la primera placa |
| Ancho de banda | 16 Hz a ≈ 27–31 kHz (−3 dB, modelo con GBW finito) | Deja pasar T1-unos hasta > 2.5 m/s. El tercer armónico de T1 solo pasa hasta ≈ 0.8 m/s: a velocidades mayores el pulso se redondea, lo que no impide detectar picos |
| Protección y recuperación | Fijación a ±0.6 V con BAV99, 47 Ω en serie; un solo acoplamiento en alterna de τ = 10 ms | Soporta los picos inducidos por la bobina de emulación (estimados en mV–V, `01` §7). Recuperación estimada < 50 ms tras saturar; **medir en T8** |
| Puntos de prueba | TP en salida de cada etapa, VREF, +3V3A, GND; jack de monitor con las dos salidas | El jack permite capturar con una interfaz de audio de 24 bits |
| ADC **y** comparador | Los dos | ADC: captura cruda, imprescindible mientras se estudia el cabezal y para decodificar con amplitud variable. Comparador con histéresis: es el camino mínimo que usaría un producto de bajo consumo (flancos → temporizador); se incluye para comparar su tasa de lectura contra la decodificación por ADC con las mismas pasadas |
| Alimentación y referencias | VBUS 5 V → AP2112K-3.3 (el mismo LDO del V5) → +3V3A solo analógica; comparador tras 10 Ω + 1 µF; LM4040-3.0 opcional como referencia del ADC del Pico | El 3V3 del Pico viene de un conmutado; no se usa para la analógica |
| Masas | Una sola red GND; retorno único hacia el MCU por J4 | En la PCB: plano continuo, etapa 1 lejos del comparador y del jack, entrada del cabezal con par trenzado corto |

## 2. Pendiente antes de hacer la PCB del AFE

1. Confirmar existencias y precio de AD8656ARZ, MCP6562-E/SN, MCP6002-I/SN, AP2112K-3.3 y pasivos el día de la compra (ver `BOM.md`).
2. Revisar pin a pin las huellas contra las hojas de datos (solo se comprobó que las huellas de biblioteca existen y que los números de pad coinciden con el símbolo).
3. Simular estabilidad de la etapa 2 con 18 pF de realimentación y la capacidad parásita del nodo sumador con los puentes.
4. Añadir, si se quiere medir el cupón A con margen, una opción de preamplificador de ~1 nV/√Hz.
5. Decidir si el Pico va en zócalo sobre la misma placa.

## 3. Placa de desarrollo y firmware

Raspberry Pi Pico 2 (RP2350; compatible con Pico/RP2040). USB nativo, ADC de 12 bits a 500 kS/s repartido entre 2 canales, PIO/temporizadores para los flancos del comparador. Su ADC no es de instrumentación (del orden de 9–10 bits efectivos **[NV]**): basta para decodificar y para SNR hasta ~50 dB si se ajusta la ganancia; para estudiar la forma de onda con más rango se usa el jack con una interfaz de audio o el osciloscopio.

Orden de trabajo: (1) captura cruda de 2 canales + compuertas, (2) detección de transiciones y decodificación F2F fuera de línea en Python, (3) el mismo algoritmo en C portable, probado en el PC contra los mismos vectores, (4) decodificación en el microcontrolador.

Validación de la decodificación: sentido de lectura (se intenta directo e invertido buscando el centinela de inicio), paridad impar por carácter, LRC, y códigos de estado distintos para "sin señal", "transiciones sin centinela", "errores de paridad", "error de LRC" y "correcto".

Estado del software (ejecutado en PC con señales sintéticas): 172 pruebas de Python y 125 comprobaciones del módulo en C superadas; el decodificador en C coincide con la referencia en Python en 39 vectores; ida y vuelta de pistas 1 y 2 en ambos sentidos, 0.05–1.5 m/s, con aceleración. Cada canal ejecuta 7 instancias del decodificador a distintas decimaciones para cubrir todo el intervalo de velocidad sin conocerla.

Lo que **no** está probado: el firmware compila sin advertencias contra el SDK real para Pico 2 y Pico (binarios en `fw/prebuilt/`), pero no ha corrido en una placa; el caudal USB no está medido y 2 canales a 250 kS/s (1 MB/s) probablemente exceden lo que da un CDC Full-Speed en continuo, por lo que el modo previsto es captura disparada con búfer en RAM o un solo canal; la temporización ADC/PIO y los umbrales por defecto solo se han ajustado en simulación. La cadena de prueba de pista 2 se cambió a `;1234567890123445=99011200123400000000?` porque la pista 2 no admite letras.

Detalle, formato de archivos y resultados de las pruebas del software: `tools/README.md` y `fw/README.md`.
