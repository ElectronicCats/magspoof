# MagHead · cabezal lector de banda magnética integrado en PCB (experimento rev A)

Trabajo de investigación y primer experimento fabricable para un sucesor del MagSpoof V5 con lectura y emulación integradas. **Nada de lo que hay aquí se ha construido ni medido todavía**: son cálculos, simulación ideal, diseños de PCB verificados por DRC y software probado con señales sintéticas.

## Recomendación

1. **Ruta principal: cabezal híbrido plano.** Bobinas impresas en la PCB (no en la capa que toca la tarjeta) alrededor de dos ranuras, y una cinta de material magnético blando de 18–50 µm que pasa por las ranuras y forma polos y entrehierro sobre la cara de la PCB. El análisis muestra que dos láminas delgadas coplanares leen igual que un cabezal de anillo del mismo entrehierro; el núcleo no necesita altura. Añade ~0.1 mm al espesor de la placa.
2. **La bobina impresa sin núcleo no sirve como lector de pista 1** (la pista mínima de PCB ya es más ancha que la separación entre transiciones, y equivale a media espira), **pero sí se fabrica como instrumento**: mide el flujo absoluto de la banda y la pérdida por separación, que son las incógnitas que hoy dejan la señal del híbrido con un factor 3 de incertidumbre.
3. **Magnetorresistivos: no en esta tanda.** No hay ningún sensor con distribución establecida cuya geometría esté verificada para 210 bpi; los candidatos solo son plausibles para pista 2 y faltan dos datos del fabricante.
4. **Primero pista 2, después pista 1 con el mismo cabezal** (el cupón se recoloca 3.30 mm con pasadores). Pista 2 valida la cadena; pista 1 decide si la geometría sirve.
5. El riesgo dominante no es el entrehierro ni el ruido, sino **mantener la banda a ≤ 25 µm del polo** con una superficie plana: en pista 1 cada micrómetro cuesta 0.45 dB.

Objetivo mecánico que sale de simular el decodificador: PW50 ≤ ~100 µm en pista 1, es decir separación banda–polo ≲ 35 µm con entrehierro a tope de 25 µm y ≲ 15–20 µm con el de solape.

Números clave (estimaciones, ver `docs/01`): señal del cupón H ≈ 45–250 µV de pico a 19 cm/s (15–50 veces menos que un cabezal comercial), fuente de ≈ 12 Ω, SNR estimada ≥ 26 dB en el peor caso con el frente analógico propuesto.

## Qué se propone fabricar

| Pieza | Qué es |
|---|---|
| `hw/coupon_H` | Cupón híbrido, 4 capas 0.8 mm: 2 sitios × (2 bobinas de 36 espiras en serie-oposición + 2 ranuras). Cinco variantes de ensamblaje sobre la misma PCB |
| `hw/coupon_A` | Cupón de pistas al aire, 2 capas: 3 pistas simples + 1 meandro adaptado a pista 2 |
| `hw/fixture` | Base con lengüetas de presión fresadas y compuertas ópticas, y separador/guía de 1.0 mm. Con el cupón forman el "sándwich" de 2.8 mm |
| `hw/afe` | Frente analógico de 2 canales: esquemático y PCB de 90 × 60 mm, 4 capas |

## Mapa del repositorio

| Ruta | Contenido |
|---|---|
| `docs/01_investigacion_y_calculos.md` | MagSpoof V5 verificado, ISO 7811, física, resultados del modelo, comparación de arquitecturas, fuentes |
| `docs/02_cupones_y_ensamblaje.md` | Geometría, stackup, variantes, procedimiento de ensamblaje, tolerancias, presupuesto de espesor |
| `docs/03_frente_analogico_y_adquisicion.md` | AFE, elección ADC/comparador, placa de desarrollo |
| `docs/04_plan_de_pruebas.md` | Instrumentación, pruebas T0–T10, métricas L1/L2/L3, puertas de decisión |
| `docs/05_incertidumbres_y_pendientes.md` | Parámetros desconocidos, estado de cada entregable, excepciones de DRC, lista previa al pedido |
| `docs/BOM.md` | Fabricantes, números de parte y canales |
| `calc/head_model.py`, `calc/out/` | Modelo: sensibilidad 2D, formas de onda F2F, eficiencia, amplitudes |
| `drawings/` | Secciones y detalle del entrehierro acotados (SVG + PNG, generados por script) |
| `hw/gen_pcbs.py`, `hw/build.sh` | Generador paramétrico de las PCBs, DRC y exportación |
| `hw/*/fab_*`, `hw/*/*_revA_gerbers.zip` | Gerbers y taladros **candidatos**, no liberados |
| `fw/` | Firmware de captura para Pico 2 y decodificador F2F portable en C |
| `tools/` | Síntesis de señal, decodificación, captura, métricas e informes en Python |

## Verificaciones hechas

- KiCad 9.0.9: DRC de las cuatro tarjetas con 0 errores y 0 conexiones pendientes; ERC del AFE con 0 errores y 0 advertencias; PCB del AFE con DRC y paridad de esquemático en 0 errores.
- Comprobación geométrica propia de separación entre espiras (el DRC no la cubre al ser una sola red): mínimo 0.127 mm, 0 violaciones.
- Netlist del AFE contra tabla independiente: coincide.
- Software: 172 pruebas en Python y 125 comprobaciones en C superadas con señales sintéticas; el firmware compila para Pico 2 y Pico con el SDK real, sin probar en placa.
- Solver de campo contra la solución analítica de Karlqvist: 1.5 % en el pico.

## Qué falta para fabricar

La lista completa está en `docs/05`, §4. Lo esencial: revisión humana de los diseños, confirmar capacidades del fabricante de PCB (ranuras de 1.0 mm, 0.127 mm en 4 capas de 0.8 mm), verificar la huella del sensor óptico contra su hoja de datos, tener el material magnético confirmado y elegir el cabezal comercial de referencia.

## Reproducir

```sh
pip install numpy scipy matplotlib cairosvg
python3 calc/head_model.py          # modelo y figuras
python3 drawings/make_drawings.py   # dibujos
sh hw/build.sh                      # PCBs + DRC + Gerbers (usa la imagen Docker kicad/kicad:9.0)
sh hw/afe/build.sh                  # esquemático + ERC + netlist
```

Licencia: la del repositorio (hardware abierto, ver `LICENSE_HARDWARE`).
