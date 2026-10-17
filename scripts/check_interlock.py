#!/usr/bin/env python3
"""Re-read the actual schematic and PCB, reconcile every pad, and run KiCad DRC.

Requires KiCad 7 pcbnew in this Python interpreter and kicad-cli on PATH (or
--kicad). This checks a test coupon only; it is not an electrical simulation.
"""
import argparse
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kicad',default='kicad-cli');args=parser.parse_args()
    directory=ROOT/'hardware/pcb/interlock-test-coupon'
    schematic=ROOT/'hardware/schematics/interlock.kicad_sch'
    xml=schematic.with_suffix('.xml')
    subprocess.run([args.kicad,'sch','export','netlist','--format','kicadxml','--output',str(xml),str(schematic)],check=True)
    subprocess.run([args.kicad,'sch','export','netlist','--output',str(schematic.with_suffix('.net')),str(schematic)],check=True)
    expected={(r['ref'],r['pin']):r['net'] for r in csv.DictReader((directory/'connections.csv').open())}
    actual_schematic={}
    for net in ET.parse(xml).findall('./nets/net'):
        for node in net.findall('node'):
            actual_schematic[(node.attrib['ref'],node.attrib['pin'])]=net.attrib['name'].lstrip('/')
    board=k.LoadBoard(str(directory/'interlock-test.kicad_pcb'));board.BuildConnectivity()
    actual_board={(fp.GetReference(),pad.GetNumber()):pad.GetNetname().lstrip('/') for fp in board.GetFootprints() for pad in fp.Pads()}
    if expected!=actual_schematic or expected!=actual_board:
        raise RuntimeError('Schematic / PCB / connection CSV disagree')
    report=ROOT/'docs/evidence/interlock-drc.txt'
    k.WriteDRCReport(board,str(report),k.EDA_UNITS_MILLIMETRES,True)
    text=report.read_text();errors=len(re.findall(r'Severity: error',text));warnings=len(re.findall(r'Severity: warning',text))
    unconnected=int(re.search(r'Found (\d+) unconnected pads',text).group(1))
    result={'evidence_level':2,'scope':'3.3V interlock test coupon only','pads_reconciled':len(expected),
            'nets':len(set(expected.values())),'schematic_csv_pcb_match':True,
            'drc_errors':errors,'drc_warnings':warnings,'unconnected_pads':unconnected,
            'electrical_behavior_tested':False,'manufacturing_release':False,
            'remaining':'External-library metadata warnings and independent package/pinout review remain. IO back-power and optical obstruction are not addressed.'}
    (ROOT/'docs/evidence/interlock-netlist-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if errors or unconnected:raise SystemExit(1)


if __name__=='__main__':main()
