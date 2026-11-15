#!/bin/sh
# Regenera todo: esquematico -> ERC -> PDF/netlist/BOM -> verificacion de netlist.
set -e
cd "$(dirname "$0")"
python3 gen_afe_sch.py
./run_kicad.sh sch erc --severity-all --format json -o erc.json maghead_afe.kicad_sch
python3 erc_summary.py -v erc.json
./run_kicad.sh sch export pdf -o maghead_afe.pdf maghead_afe.kicad_sch
./run_kicad.sh sch export netlist -o maghead_afe.net maghead_afe.kicad_sch
./run_kicad.sh sch export bom -o maghead_afe_bom.csv \
  --fields 'Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY},${DNP}' \
  --labels 'Refs,Valor,Huella,MPN,Fabricante,Cant,DNP' \
  --group-by 'Value,Footprint,MPN,${DNP}' --ref-range-delimiter '' maghead_afe.kicad_sch
python3 check_netlist.py maghead_afe.net
