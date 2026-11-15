#!/bin/sh
# Regenera todo: esquematico -> ERC -> PDF/netlist/BOM -> verificacion de netlist
#               -> PCB (colocacion + ruteo + zonas) -> DRC con paridad -> verificacion de pads
#               -> vistas SVG/PNG -> Gerber + taladros + posiciones.
# Requiere docker con la imagen kicad/kicad:9.0. Uso: sh build.sh
set -e
cd "$(dirname "$0")"
N=maghead_afe
python3 gen_afe_sch.py
./run_kicad.sh sch erc --severity-all --format json -o erc.json $N.kicad_sch
python3 erc_summary.py -v erc.json
./run_kicad.sh sch export pdf -o $N.pdf $N.kicad_sch
./run_kicad.sh sch export netlist -o $N.net $N.kicad_sch
./run_kicad.sh sch export bom -o ${N}_bom.csv \
  --fields 'Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY},${DNP}' \
  --labels 'Refs,Valor,Huella,MPN,Fabricante,Cant,DNP' \
  --group-by 'Value,Footprint,MPN,${DNP}' --ref-range-delimiter '' $N.kicad_sch
python3 check_netlist.py $N.net

# ---- PCB (gen_afe_pcb.py necesita pcbnew: corre dentro del contenedor)
chmod -R a+rwX . 2>/dev/null || true
ROOT="$(cd ../.. && pwd)"
docker run --rm --user 0 -v "$ROOT":/work -w /work/hw/afe kicad/kicad:9.0 python3 gen_afe_pcb.py 2>&1 | grep -v Debug
test -s $N.kicad_pcb
rm -f $N.kicad_prl
./run_kicad.sh pcb drc --schematic-parity --severity-all --format json --units mm -o drc.json $N.kicad_pcb 2>&1 | grep -v Debug
python3 drc_summary.py drc.json
python3 check_pcb.py $N.kicad_pcb $N.net

# ---- vistas
for v in "F:F.Cu,F.SilkS,Edge.Cuts" "B:B.Cu,Edge.Cuts" "In1:In1.Cu,Edge.Cuts" "In2:In2.Cu,Edge.Cuts" "silk:F.SilkS,F.Mask,Edge.Cuts"; do
  ./run_kicad.sh pcb export svg --layers "${v#*:}" --mode-single --page-size-mode 2 --exclude-drawing-sheet \
    -o ${N}_${v%%:*}.svg $N.kicad_pcb 2>&1 | grep -v Debug | tail -1
done
python3 - <<'PY' || echo "(sin cairosvg: no se generan PNG)"
import cairosvg
for v in ("F", "B", "silk"):
    cairosvg.svg2png(url="maghead_afe_%s.svg" % v, write_to="maghead_afe_%s.png" % v, output_width=2700,
                     background_color="black")
PY

# ---- fabricacion (candidato rev A; ver PCB_NOTES.md antes de ordenar)
F=fab_$N
mkdir -p $F; rm -f $F/*; chmod a+rwx $F
./run_kicad.sh pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,F.SilkS,B.SilkS,Edge.Cuts \
  --subtract-soldermask --no-protel-ext -o $F/ $N.kicad_pcb 2>&1 | grep -v Debug | tail -1
./run_kicad.sh pcb export drill --format excellon --drill-origin absolute --excellon-units mm \
  --generate-map --map-format gerberx2 -o $F/ $N.kicad_pcb 2>&1 | grep -v Debug | tail -1
./run_kicad.sh pcb export pos --format csv --units mm --side front --exclude-dnp \
  -o ${N}_pos.csv $N.kicad_pcb 2>&1 | grep -v Debug | tail -1
rm -f ${N}_revA_gerbers.zip
(cd $F && zip -q -r ../${N}_revA_gerbers.zip .)
chmod -R a+rwX . 2>/dev/null || true
echo "build OK"
