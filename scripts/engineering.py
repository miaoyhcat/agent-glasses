#!/usr/bin/env python3
"""Reproduce H1 mass, energy, paraxial optics and thermal sensitivity budgets.

Only arithmetic is validated. Unknown inputs do not become measurements when
processed by this program. All state powers are exclusive regulated-rail loads.
"""
import csv
import itertools
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def calculate():
    p=json.loads((ROOT/'hardware/power/budget.json').read_text())
    b=p['battery'];nominal=b['cells_parallel']*b['mah_each']/1000*b['nominal_v']
    usable=nominal*b['usable_fraction']*b['end_of_life_capacity']
    eta=p['converter_efficiency'];quiescent=p['battery_quiescent_w']
    powers={name:item['rail_w']/eta+quiescent for name,item in p['states'].items()}
    profiles={}
    for name,shares in p['profiles'].items():
        if any(v<0 for v in shares.values()) or abs(sum(shares.values())-1)>1e-10:raise ValueError('profile fractions must sum to 1')
        power=sum(powers[k]*v for k,v in shares.items())
        profiles[name]={'battery_w':round(power,5),'hours_EOL':round(usable/power,3),'hours_new':round(nominal*b['usable_fraction']/power,3),'minutes_per_8h':{k:round(v*480,2) for k,v in shares.items()}}
    mass=list(csv.DictReader((ROOT/'hardware/bom/mass-budget.csv').open()))
    mass_totals={key:round(sum(float(r['qty'])*float(r[key]) for r in mass),2) for key in ['unit_g','min_unit_g','max_unit_g']}
    placements=json.loads((ROOT/'hardware/mechanical/mass-placement.json').read_text())
    group_mass={r['assembly']:float(r['qty'])*float(r['unit_g']) for r in mass}
    center={axis:sum(group_mass[r['group']]*r['fraction']*r[axis] for r in placements['placements'])/mass_totals['unit_g'] for axis in ['x','z']}
    nose_fraction=1-center['z']/placements['ear_support_z_mm']
    mechanical={'center_of_mass_mm':center,'nose_vertical_load_N':mass_totals['unit_g']/1000*9.80665*nose_fraction,
                'nose_average_pressure_kPa':mass_totals['unit_g']/1000*9.80665*nose_fraction/(placements['nose_contact_area_total_mm2']*1e-6)/1000}
    # Fixed scenario grid; not a posterior probability of achieving the targets.
    rows=[];shares=p['profiles']['mixed_defined']
    for idle,extra,capacity in itertools.product(p['sensitivity']['idle_power_multipliers'],p['sensitivity']['optics_hud_extra_w'],p['sensitivity']['capacity_factors']):
        scenario=dict(powers);scenario['connected_idle']=(p['states']['connected_idle']['rail_w']*idle)/eta+quiescent
        scenario['hud']+=extra/eta;power=sum(scenario[k]*v for k,v in shares.items())
        energy=nominal*b['usable_fraction']*capacity
        rows.append({'idle_factor':idle,'extra_hud_rail_w':extra,'capacity_factor':capacity,'hours':round(energy/power,3)})
    o=json.loads((ROOT/'hardware/optics/specification.json').read_text())
    w=o['panel_width_px']*o['pitch_um']/1000;h=o['panel_height_px']*o['pitch_um']/1000;f=o['collimator_focal_mm']
    def angle(size):return math.degrees(2*math.atan(size/(2*f)))
    # 1/f=1/u+1/v, virtual image v=-L.
    u=1/(1/f+1/o['virtual_distance_mm'])
    optics={'active_mm':[round(w,4),round(h,4)],'fov_deg':[round(angle(w),3),round(angle(h),3),round(angle(math.hypot(w,h)),3)],
            'object_distance_mm':round(u,5),'horizontal_pixels_per_degree':round(o['panel_width_px']/angle(w),3),
            'radiance_budget_cd_m2':o['panel_peak_luminance_cd_m2']*o['combiner_reflectance_assumption']*o['path_transmission_assumption'],
            'focus_sensitivity':[]}
    for error in o['focal_placement_errors_mm']:
        vergence=1000*(1/f-1/(u+error))
        optics['focus_sensitivity'].append({'placement_error_mm':error,'image_vergence_diopter':round(vergence,4)})
    thermal=[]
    for state,theta,ambient in itertools.product(['hud','record','transfer'],p['thermal']['effective_k_per_w'],p['thermal']['ambient_c']):
        thermal.append({'state':state,'ambient_c':ambient,'k_per_w':theta,'surface_proxy_c':round(ambient+powers[state]*theta,2)})
    costs=json.loads((ROOT/'hardware/bom/cost-budget.json').read_text())
    return {'evidence_level':3,'physical_tests_performed':False,'nominal_Wh':round(nominal,5),'usable_EOL_Wh':round(usable,5),
        'state_battery_w':powers,'profiles':profiles,'mass_g':mass_totals,'mechanical_statics':mechanical,'sensitivity':rows,'optics':optics,'thermal_lumped_sensitivity':thermal,
        'prototype_cost_allocation_USD':[sum(i['low'] for i in costs['items']),sum(i['high'] for i in costs['items'])],
        'conclusion':'H1 target only; no complete manufacturing release. 50g target misses nominal mass. 8h mixed use depends on unmeasured low-power firmware/optics. Continuous video and warm ambient operation require measured thermal limits.'}


if __name__=='__main__':
    result=calculate();out=ROOT/'docs/evidence/engineering-results.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['nominal_Wh','usable_EOL_Wh','mass_g','prototype_cost_allocation_USD']},indent=2))
    print(json.dumps(result['profiles'],ensure_ascii=False,indent=2))
    model=json.loads((ROOT/'docs/architecture-candidates.json').read_text());weights=model['weights']
    scores={c['id']:round(sum(weights[k]*c['scores'][k] for k in weights),4) for c in model['candidates']}
    sensitivity=[]
    for energy,procurement in itertools.product([.10,.25,.40],[.10,.25,.40]):
        rest=sum(v for k,v in weights.items() if k not in {'energy','procurement'});w={k:(energy if k=='energy' else procurement if k=='procurement' else value*(1-energy-procurement)/rest) for k,value in weights.items()}
        s={c['id']:round(sum(w[k]*c['scores'][k] for k in w),3) for c in model['candidates']}
        sensitivity.append({'energy_weight':energy,'procurement_weight':procurement,'scores':s})
    (ROOT/'docs/evidence/architecture-ranking.json').write_text(json.dumps({'scores':scores,'sensitivity':sensitivity,'all_candidates_fail_manufacturing_release_gates':True,'development_choice':'A-H1 conditional; C-platform only for earlier SDK display experiments'},indent=2)+'\n')
