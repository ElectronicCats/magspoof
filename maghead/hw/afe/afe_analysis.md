# Analisis del AFE MagHead (rev A)

Generado por `afe_analysis.py`. Prototipo de laboratorio, no liberado para fabricacion.

## Supuestos del modelo

- Cabezal: f.e.m. en serie con 13 ohm y 100 uH; HEAD_N unido a VREF por R100 = 0R.
- Op-amp AD8656: un solo polo, GBW = 28 MHz; en blanco = 2.7 nV/rtHz (dato de hoja a 10 kHz).
- **Supuesto**: esquina 1/f de en = 1.2 kHz (equivale a ~4 nV/rtHz a 1 kHz). No verificado contra la hoja de datos.
- **Supuesto**: capacidad de entrada + pistas = 10 pF; R101/C101/C102 no montados (DNP).
- **Supuesto**: ruido del buffer de VREF (MCP6002) = 29 nV/rtHz blanco. Aparece con ganancia 1 en la salida
  (por encima del paso alto), por eso se divide por G1*G2 al referirlo a la entrada.
- Ruido de corriente de los op-amp CMOS despreciado (fA/rtHz sobre <100 ohm). T = 300 K.
- No incluidos: ruido/cuantizacion del ADC del MCU, ruido de alimentacion (PSRR), captacion magnetica/EMI,
  capacidad del BAV99, tolerancias de componentes, microfonia/coeficiente de tension de C104 (X5R).

## Ganancias exactas (valores nominales)

Etapa 1 (no inversora, G1 = 1 + R103/Rg):

| JP101/JP201 | Rg | G1 | G1 (dB) |
|---|---|---|---|
| abierto | 100.0000 ohm | x11.000 | 20.83 |
| cerrado | 9.9099 ohm | x101.909 | 40.16 |

Etapa 2 (inversora, G2 = Rf/R106):

| Jumpers cerrados | Rf paralelo | G2 | Cf total | polo Rf*Cf |
|---|---|---|---|---|
| ninguno | 200.0000 k | x200.000 | 18 pF | 44.2 kHz |
| JP102 | 39.9360 k | x39.936 | 100 pF | 39.9 kHz |
| JP103 | 9.5238 k | x9.524 | 408 pF | 41.0 kHz |
| JP104 | 1.9802 k | x1.980 | 2218 pF | 36.2 kHz |
| JP102+JP103 | 7.9974 k | x7.997 | 490 pF | 40.6 kHz |
| JP102+JP104 | 1.9046 k | x1.905 | 2300 pF | 36.3 kHz |
| JP103+JP104 | 1.6529 k | x1.653 | 2608 pF | 36.9 kHz |
| JP102+JP103+JP104 | 1.5999 k | x1.600 | 2690 pF | 37.0 kHz |

Paso alto C104*R106 = 15.92 Hz; polo R103*C103 = 159.2 kHz; polo R111*C111 = 72.34 kHz.

## Funcion de transferencia CABEZAL -> ADC

Ganancia a 1 kHz y banda a -3 dB (respecto a 1 kHz), con todos los polos y el GBW finito.

| G1 | Jumpers etapa 2 | G total nominal | |H| a 1 kHz | dB | f -3dB inf | f -3dB sup |
|---|---|---|---|---|---|---|
| x11.0 | ninguno | x2200.0 | x2198.7 | 66.8 | 15.9 Hz | 27.7 kHz |
| x11.0 | JP102 | x439.3 | x439.0 | 52.9 | 15.9 Hz | 30.0 kHz |
| x11.0 | JP103 | x104.8 | x104.7 | 40.4 | 15.9 Hz | 31.4 kHz |
| x11.0 | JP104 | x21.8 | x21.8 | 26.8 | 15.9 Hz | 29.2 kHz |
| x11.0 | JP102+JP103 | x88.0 | x87.9 | 38.9 | 15.9 Hz | 31.4 kHz |
| x11.0 | JP102+JP104 | x21.0 | x20.9 | 26.4 | 15.9 Hz | 29.3 kHz |
| x11.0 | JP103+JP104 | x18.2 | x18.2 | 25.2 | 15.9 Hz | 29.7 kHz |
| x11.0 | JP102+JP103+JP104 | x17.6 | x17.6 | 24.9 | 15.9 Hz | 29.7 kHz |
| x101.9 | ninguno | x20381.8 | x20369.6 | 86.2 | 15.9 Hz | 26.9 kHz |
| x101.9 | JP102 | x4069.8 | x4067.4 | 72.2 | 15.9 Hz | 29.0 kHz |
| x101.9 | JP103 | x970.6 | x970.0 | 59.7 | 15.9 Hz | 30.2 kHz |
| x101.9 | JP104 | x201.8 | x201.7 | 46.1 | 15.9 Hz | 28.2 kHz |
| x101.9 | JP102+JP103 | x815.0 | x814.5 | 58.2 | 15.9 Hz | 30.0 kHz |
| x101.9 | JP102+JP104 | x194.1 | x194.0 | 45.8 | 15.9 Hz | 28.2 kHz |
| x101.9 | JP103+JP104 | x168.4 | x168.3 | 44.5 | 15.9 Hz | 28.5 kHz |
| x101.9 | JP102+JP103+JP104 | x163.0 | x162.9 | 44.2 | 15.9 Hz | 28.5 kHz |

Grafica: `afe_tf.png` (un jumper de etapa 2 cerrado cada vez = ajustes nominales x200/x40/x9.5/x1.9).

## Balance de ruido referido a la entrada (100 Hz - 20 kHz)

Valores en nV rms integrados en la banda y densidad a 10 kHz en nV/rtHz.

### G1 x101.9, etapa 2 sin jumper (G2 x200, total x20382)

| Contribuyente | nV rms | nV/rtHz @10 kHz | % de la potencia |
|---|---|---|---|
| Bobina cabezal 13R (termico) | 65.5 | 0.464 | 2.0 |
| R102 47R | 124.5 | 0.882 | 7.2 |
| Red de ganancia Rg||R103 | 56.9 | 0.403 | 1.5 |
| U1 en (2.7 nV/rtHz + 1/f) | 437.5 | 2.857 | 89.2 |
| Etapa 2: R106 1k | 5.6 | 0.040 | 0.0 |
| Etapa 2: Rf | 0.4 | 0.003 | 0.0 |
| Etapa 2: U2 en x (1+G2)/G2 | 4.3 | 0.028 | 0.0 |
| Buffer VREF (U3) /(G1 G2) | 0.2 | 0.001 | 0.0 |
| R111 1k /(G1 G2) | 0.0 | 0.000 | 0.0 |
| **TOTAL** | **463.1** | **3.053** | 100 |

### G1 x101.9, etapa 2 JP102 (G2 x39.94, total x4070)

| Contribuyente | nV rms | nV/rtHz @10 kHz | % de la potencia |
|---|---|---|---|
| Bobina cabezal 13R (termico) | 65.5 | 0.464 | 2.0 |
| R102 47R | 124.5 | 0.882 | 7.2 |
| Red de ganancia Rg||R103 | 56.9 | 0.403 | 1.5 |
| U1 en (2.7 nV/rtHz + 1/f) | 437.5 | 2.857 | 89.2 |
| Etapa 2: R106 1k | 5.6 | 0.040 | 0.0 |
| Etapa 2: Rf | 0.9 | 0.006 | 0.0 |
| Etapa 2: U2 en x (1+G2)/G2 | 4.4 | 0.029 | 0.0 |
| Buffer VREF (U3) /(G1 G2) | 1.0 | 0.007 | 0.0 |
| R111 1k /(G1 G2) | 0.1 | 0.001 | 0.0 |
| **TOTAL** | **463.1** | **3.053** | 100 |

### G1 x11.0, etapa 2 sin jumper (G2 x200, total x2200)

| Contribuyente | nV rms | nV/rtHz @10 kHz | % de la potencia |
|---|---|---|---|
| Bobina cabezal 13R (termico) | 65.5 | 0.464 | 1.7 |
| R102 47R | 124.5 | 0.882 | 6.3 |
| Red de ganancia Rg||R103 | 173.1 | 1.227 | 12.2 |
| U1 en (2.7 nV/rtHz + 1/f) | 437.5 | 2.857 | 78.0 |
| Etapa 2: R106 1k | 52.2 | 0.370 | 1.1 |
| Etapa 2: Rf | 3.7 | 0.026 | 0.0 |
| Etapa 2: U2 en x (1+G2)/G2 | 40.0 | 0.261 | 0.7 |
| Buffer VREF (U3) /(G1 G2) | 1.9 | 0.013 | 0.0 |
| R111 1k /(G1 G2) | 0.3 | 0.002 | 0.0 |
| **TOTAL** | **495.5** | **3.297** | 100 |

### G1 x11.0, etapa 2 JP104 (G2 x1.98, total x22)

| Contribuyente | nV rms | nV/rtHz @10 kHz | % de la potencia |
|---|---|---|---|
| Bobina cabezal 13R (termico) | 65.5 | 0.464 | 1.5 |
| R102 47R | 124.5 | 0.882 | 5.4 |
| Red de ganancia Rg||R103 | 173.1 | 1.227 | 10.5 |
| U1 en (2.7 nV/rtHz + 1/f) | 437.5 | 2.857 | 67.2 |
| Etapa 2: R106 1k | 52.2 | 0.370 | 1.0 |
| Etapa 2: Rf | 37.1 | 0.263 | 0.5 |
| Etapa 2: U2 en x (1+G2)/G2 | 59.9 | 0.391 | 1.3 |
| Buffer VREF (U3) /(G1 G2) | 187.8 | 1.331 | 12.4 |
| R111 1k /(G1 G2) | 26.4 | 0.187 | 0.2 |
| **TOTAL** | **533.7** | **3.582** | 100 |

### Resumen para todos los ajustes

Ruido en ADC = integral de S_in(f)*|H(f)|^2 en 100 Hz - 20 kHz (incluye la forma real de la respuesta).

| G1 | Jumpers etapa 2 | G total | Ruido entrada (nV rms) | Solo cabezal (nV rms) | Factor de ruido (dB) | Ruido en ADC (uV rms) |
|---|---|---|---|---|---|---|
| x11.0 | ninguno | x2200.0 | 495.5 | 65.5 | 17.6 | 1030.0 |
| x11.0 | JP102 | x439.3 | 495.7 | 65.5 | 17.6 | 207.4 |
| x11.0 | JP103 | x104.8 | 497.7 | 65.5 | 17.6 | 49.9 |
| x11.0 | JP104 | x21.8 | 533.7 | 65.5 | 18.2 | 11.0 |
| x11.0 | JP102+JP103 | x88.0 | 498.4 | 65.5 | 17.6 | 41.9 |
| x11.0 | JP102+JP104 | x21.0 | 536.6 | 65.5 | 18.3 | 10.7 |
| x11.0 | JP103+JP104 | x18.2 | 548.9 | 65.5 | 18.5 | 9.5 |
| x11.0 | JP102+JP103+JP104 | x17.6 | 552.2 | 65.5 | 18.5 | 9.2 |
| x101.9 | ninguno | x20381.8 | 463.1 | 65.5 | 17.0 | 8906.5 |
| x101.9 | JP102 | x4069.8 | 463.1 | 65.5 | 17.0 | 1792.2 |
| x101.9 | JP103 | x970.6 | 463.2 | 65.5 | 17.0 | 429.1 |
| x101.9 | JP104 | x201.8 | 463.6 | 65.5 | 17.0 | 88.7 |
| x101.9 | JP102+JP103 | x815.0 | 463.2 | 65.5 | 17.0 | 360.2 |
| x101.9 | JP102+JP104 | x194.1 | 463.7 | 65.5 | 17.0 | 85.4 |
| x101.9 | JP103+JP104 | x168.4 | 463.8 | 65.5 | 17.0 | 74.2 |
| x101.9 | JP102+JP103+JP104 | x163.0 | 463.9 | 65.5 | 17.0 | 71.8 |

Lectura: con G1 = x102 el ruido lo domina el propio AD8656 (en + 1/f) seguido de R102; con G1 = x11
pesa ademas la red de ganancia (100R||1k) y, a ganancias bajas de etapa 2, el buffer de VREF y U2.
Estos numeros son de MODELO (valores tipicos); no hay medidas sobre hardware.

