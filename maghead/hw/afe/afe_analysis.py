#!/usr/bin/env python3
"""Analisis de pequena senal y balance de ruido del AFE MagHead (rev A).

  - Funcion de transferencia CABEZAL (f.e.m.) -> ADC para cada ajuste de ganancia,
    10 Hz .. 1 MHz, con modelo de un polo del op-amp (GBW 28 MHz), paso alto
    C104/R106, polo R103||C103, polo Rf||Cf de la etapa 2 y polo R111/C111.
  - Balance de ruido referido a la entrada para un cabezal de 13 ohm / 100 uH,
    integrado en 100 Hz .. 20 kHz.
Salida: afe_tf.png y afe_analysis.md (tambien por stdout).
"""
import os
import itertools
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
k_B, T = 1.380649e-23, 300.0
FOURKT = 4 * k_B * T

# ---------------- valores del esquematico ----------------
R_HEAD, L_HEAD = 13.0, 100e-6          # cabezal de referencia
R102 = 47.0
R103, C103 = 1e3, 1e-9
R104, R105 = 100.0, 11.0
C104, R106 = 10e-6, 1e3
BRANCH = {None: (200e3, 18e-12), "JP102": (49.9e3, 82e-12),
          "JP103": (10e3, 390e-12), "JP104": (2e3, 2.2e-9)}
R111, C111 = 1e3, 2.2e-9
# ---------------- supuestos (declarados en el .md) ----------------
GBW = 28e6            # AD8656, modelo de un polo A(f) = GBW/(j f)
EN_W = 2.7e-9         # AD8656 en blanco (hoja de datos, 10 kHz)
FC_1F = 1.2e3         # SUPUESTO: esquina 1/f, de en ~ 4 nV/rtHz a 1 kHz
C_IN = 10e-12         # SUPUESTO: capacidad de entrada op-amp + pistas (C102 es DNP)
EN_VREF = 29e-9       # SUPUESTO: MCP6002 (buffer de VREF) ~29 nV/rtHz, blanco
F1, F2 = 100.0, 20e3  # banda de integracion


def par(*z):
    return 1.0 / sum(1.0 / x for x in z)


def stage1_gain(jp_closed):
    rg = par(R104, R105) if jp_closed else R104
    return 1 + R103 / rg, rg


def stage2_net(closed):
    """closed: tupla de jumpers cerrados -> (Rf, Cf)."""
    rs = [BRANCH[None][0]] + [BRANCH[j][0] for j in closed]
    cs = [BRANCH[None][1]] + [BRANCH[j][1] for j in closed]
    return par(*rs), sum(cs)


def tf(f, jp1, closed):
    """H(f) = V(ADC) / f.e.m. del cabezal (compleja)."""
    s = 2j * np.pi * f
    A = GBW / (1j * f)
    # entrada: (R_head + sL + R102) contra C_IN
    h_in = 1 / (1 + s * C_IN * (R_HEAD + s * L_HEAD + R102))
    # etapa 1 no inversora
    _, rg = stage1_gain(jp1)
    zf = R103 / (1 + s * R103 * C103)
    beta = rg / (rg + zf)
    h1 = A / (1 + A * beta)
    # etapa 2 inversora con acoplo AC
    rf, cf = stage2_net(closed)
    zin = R106 + 1 / (s * C104)
    zf2 = rf / (1 + s * rf * cf)
    h2 = -(zf2 / zin) / (1 + (1 + zf2 / zin) / A)
    # filtro de salida
    h3 = 1 / (1 + s * R111 * C111)
    return h_in * h1 * h2 * h3


def noise_terms(f, jp1, closed):
    """Densidades de ruido referidas a la entrada (V^2/Hz) por contribuyente."""
    g1, rg = stage1_gain(jp1)
    rf, _ = stage2_net(closed)
    g2 = rf / R106
    one = np.ones_like(f)
    t = {
        "Bobina cabezal 13R (termico)": FOURKT * R_HEAD * one,
        "R102 47R": FOURKT * R102 * one,
        "Red de ganancia Rg||R103": FOURKT * par(rg, R103) * one,
        "U1 en (2.7 nV/rtHz + 1/f)": EN_W ** 2 * (1 + FC_1F / f),
        "Etapa 2: R106 1k": FOURKT * R106 / g1 ** 2 * one,
        "Etapa 2: Rf": FOURKT * R106 ** 2 / rf / g1 ** 2 * one,
        "Etapa 2: U2 en x (1+G2)/G2": EN_W ** 2 * (1 + FC_1F / f) * ((1 + g2) / g2) ** 2 / g1 ** 2,
        "Buffer VREF (U3) /(G1 G2)": EN_VREF ** 2 / (g1 * g2) ** 2 * one,
        "R111 1k /(G1 G2)": FOURKT * R111 / (g1 * g2) ** 2 * one,
    }
    return t, g1, g2


def integ(y, f):
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(f)))


def bw3(f, mag, ref):
    """Frecuencias de -3 dB respecto a ref (inferior, superior)."""
    ok = np.where(mag >= ref / np.sqrt(2))[0]
    return f[ok[0]], f[ok[-1]]


def main():
    out = []
    P = out.append
    f = np.logspace(1, 6, 2001)
    fn = np.logspace(np.log10(F1), np.log10(F2), 4001)
    jumpers = ["JP102", "JP103", "JP104"]
    combos = [c for n in range(4) for c in itertools.combinations(jumpers, n)]

    P("# Analisis del AFE MagHead (rev A)\n")
    P("Generado por `afe_analysis.py`. Prototipo de laboratorio, no liberado para fabricacion.\n")
    P("## Supuestos del modelo\n")
    P("- Cabezal: f.e.m. en serie con %.0f ohm y %.0f uH; HEAD_N unido a VREF por R100 = 0R." % (R_HEAD, L_HEAD * 1e6))
    P("- Op-amp AD8656: un solo polo, GBW = %.0f MHz; en blanco = %.1f nV/rtHz (dato de hoja a 10 kHz)." % (GBW / 1e6, EN_W * 1e9))
    P("- **Supuesto**: esquina 1/f de en = %.1f kHz (equivale a ~4 nV/rtHz a 1 kHz). No verificado contra la hoja de datos." % (FC_1F / 1e3))
    P("- **Supuesto**: capacidad de entrada + pistas = %.0f pF; R101/C101/C102 no montados (DNP)." % (C_IN * 1e12))
    P("- **Supuesto**: ruido del buffer de VREF (MCP6002) = %.0f nV/rtHz blanco. Aparece con ganancia 1 en la salida" % (EN_VREF * 1e9))
    P("  (por encima del paso alto), por eso se divide por G1*G2 al referirlo a la entrada.")
    P("- Ruido de corriente de los op-amp CMOS despreciado (fA/rtHz sobre <100 ohm). T = %.0f K." % T)
    P("- No incluidos: ruido/cuantizacion del ADC del MCU, ruido de alimentacion (PSRR), captacion magnetica/EMI,")
    P("  capacidad del BAV99, tolerancias de componentes, microfonia/coeficiente de tension de C104 (X5R).\n")

    # ---------------- tabla de ganancias ----------------
    P("## Ganancias exactas (valores nominales)\n")
    P("Etapa 1 (no inversora, G1 = 1 + R103/Rg):\n")
    P("| JP101/JP201 | Rg | G1 | G1 (dB) |")
    P("|---|---|---|---|")
    for jp1 in (False, True):
        g1, rg = stage1_gain(jp1)
        P("| %s | %.4f ohm | x%.3f | %.2f |" % ("cerrado" if jp1 else "abierto", rg, g1, 20 * np.log10(g1)))
    P("\nEtapa 2 (inversora, G2 = Rf/R106):\n")
    P("| Jumpers cerrados | Rf paralelo | G2 | Cf total | polo Rf*Cf |")
    P("|---|---|---|---|---|")
    for c in combos:
        rf, cf = stage2_net(c)
        P("| %s | %.4f k | x%.3f | %.0f pF | %.1f kHz |" % ("+".join(c) or "ninguno", rf / 1e3, rf / R106, cf * 1e12,
                                                         1 / (2 * np.pi * rf * cf) / 1e3))
    P("\nPaso alto C104*R106 = %.2f Hz; polo R103*C103 = %.1f kHz; polo R111*C111 = %.2f kHz.\n"
      % (1 / (2 * np.pi * R106 * C104), 1 / (2 * np.pi * R103 * C103) / 1e3, 1 / (2 * np.pi * R111 * C111) / 1e3))

    # ---------------- funcion de transferencia ----------------
    P("## Funcion de transferencia CABEZAL -> ADC\n")
    P("Ganancia a 1 kHz y banda a -3 dB (respecto a 1 kHz), con todos los polos y el GBW finito.\n")
    P("| G1 | Jumpers etapa 2 | G total nominal | |H| a 1 kHz | dB | f -3dB inf | f -3dB sup |")
    P("|---|---|---|---|---|---|---|")
    for jp1 in (False, True):
        g1, _ = stage1_gain(jp1)
        for c in combos:
            rf, _ = stage2_net(c)
            mag = np.abs(tf(f, jp1, c))
            m1k = float(np.abs(tf(np.array([1e3]), jp1, c))[0])
            lo, hi = bw3(f, mag, m1k)
            P("| x%.1f | %s | x%.1f | x%.1f | %.1f | %.1f Hz | %.1f kHz |"
              % (g1, "+".join(c) or "ninguno", g1 * rf / R106, m1k, 20 * np.log10(m1k), lo, hi / 1e3))
    P("\nGrafica: `afe_tf.png` (un jumper de etapa 2 cerrado cada vez = ajustes nominales x200/x40/x9.5/x1.9).\n")

    # ---------------- grafica ----------------
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]      # paleta categorica, orden fijo
    ink, ink2, surf = "#0b0b0b", "#52514e", "#fcfcfb"
    nominal = [(), ("JP102",), ("JP103",), ("JP104",)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), sharey=True, facecolor=surf)
    for ax, jp1 in zip(axes, (False, True)):
        g1, _ = stage1_gain(jp1)
        ax.set_facecolor(surf)
        for col, c in zip(colors, nominal):
            rf, _ = stage2_net(c)
            db = 20 * np.log10(np.abs(tf(f, jp1, c)))
            name = "%s: G2 x%.3g" % ("+".join(c) or "sin jumper", rf / R106)
            ax.semilogx(f, db, color=col, lw=2, label=name)
            i = np.searchsorted(f, 1e3)
            ax.annotate("x%.0f (%.1f dB)" % (g1 * rf / R106, db[i]), (f[i], db[i]), xytext=(0, 5),
                        textcoords="offset points", ha="center", fontsize=9, color=ink)
        ax.set_title("Etapa 1 x%.1f (JP101 %s)" % (g1, "cerrado" if jp1 else "abierto"), color=ink, fontsize=11, loc="left")
        ax.set_xlabel("Frecuencia (Hz)", color=ink2)
        ax.grid(True, which="major", color="#d9d8d3", lw=0.6)
        ax.grid(True, which="minor", color="#ecebe7", lw=0.4)
        ax.set_xlim(10, 1e6)
        ax.set_ylim(-20, 95)
        ax.tick_params(colors=ink2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color("#b5b4ae")
    axes[0].set_ylabel("|V(ADC) / f.e.m. cabezal| (dB)", color=ink2)
    axes[1].legend(title="Etapa 2", frameon=False, fontsize=9, loc="lower left", labelcolor=ink)
    fig.suptitle("MagHead AFE rev A: respuesta cabezal -> ADC (13 ohm / 100 uH, GBW 28 MHz)", color=ink, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "afe_tf.png"), dpi=130, facecolor=surf)

    # ---------------- ruido ----------------
    P("## Balance de ruido referido a la entrada (100 Hz - 20 kHz)\n")
    P("Valores en nV rms integrados en la banda y densidad a 10 kHz en nV/rtHz.\n")
    for jp1, c in ((True, ()), (True, ("JP102",)), (False, ()), (False, ("JP104",))):
        terms, g1, g2 = noise_terms(fn, jp1, c)
        P("### G1 x%.1f, etapa 2 %s (G2 x%.4g, total x%.0f)\n" % (g1, "+".join(c) or "sin jumper", g2, g1 * g2))
        P("| Contribuyente | nV rms | nV/rtHz @10 kHz | % de la potencia |")
        P("|---|---|---|---|")
        tot = sum(terms.values())
        tot_i = integ(tot, fn)
        i10 = np.searchsorted(fn, 1e4)
        for name, s in terms.items():
            P("| %s | %.1f | %.3f | %.1f |" % (name, np.sqrt(integ(s, fn)) * 1e9, np.sqrt(s[i10]) * 1e9, 100 * integ(s, fn) / tot_i))
        P("| **TOTAL** | **%.1f** | **%.3f** | 100 |\n" % (np.sqrt(tot_i) * 1e9, np.sqrt(tot[i10]) * 1e9))

    P("### Resumen para todos los ajustes\n")
    P("Ruido en ADC = integral de S_in(f)*|H(f)|^2 en 100 Hz - 20 kHz (incluye la forma real de la respuesta).\n")
    P("| G1 | Jumpers etapa 2 | G total | Ruido entrada (nV rms) | Solo cabezal (nV rms) | Factor de ruido (dB) | Ruido en ADC (uV rms) |")
    P("|---|---|---|---|---|---|---|")
    summary = []
    for jp1 in (False, True):
        for c in combos:
            terms, g1, g2 = noise_terms(fn, jp1, c)
            tot = sum(terms.values())
            vin = np.sqrt(integ(tot, fn))
            vcoil = np.sqrt(integ(terms["Bobina cabezal 13R (termico)"], fn))
            vout = np.sqrt(integ(tot * np.abs(tf(fn, jp1, c)) ** 2, fn))
            summary.append((g1, c, g1 * g2, vin, vout))
            P("| x%.1f | %s | x%.1f | %.1f | %.1f | %.1f | %.1f |"
              % (g1, "+".join(c) or "ninguno", g1 * g2, vin * 1e9, vcoil * 1e9, 20 * np.log10(vin / vcoil), vout * 1e6))
    P("\nLectura: con G1 = x102 el ruido lo domina el propio AD8656 (en + 1/f) seguido de R102; con G1 = x11")
    P("pesa ademas la red de ganancia (100R||1k) y, a ganancias bajas de etapa 2, el buffer de VREF y U2.")
    P("Estos numeros son de MODELO (valores tipicos); no hay medidas sobre hardware.\n")

    txt = "\n".join(out) + "\n"
    open(os.path.join(HERE, "afe_analysis.md"), "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
