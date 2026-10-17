#!/usr/bin/env python3
"""Generate editable CadQuery-derived STEP assembly and individual STL fixtures."""
import json
from pathlib import Path
import cadquery as cq

ROOT=Path(__file__).resolve().parents[1]


def geometry(p):
    d=p['front_depth']
    rings=[]
    for sign in [-1,1]:
        ring=(cq.Workplane('XY').center(sign*p['lens_center_x'],0)
              .ellipse(p['rim_outer_rx'],p['rim_outer_ry']).ellipse(p['lens_opening_rx'],p['lens_opening_ry']).extrude(d))
        rings.append(ring)
    front=rings[0].union(rings[1]).union(cq.Workplane('XY').box(20,5,d,centered=(True,True,False)).translate((0,9.5,0)))
    for sign in [-1,1]:
        front=front.union(cq.Workplane('XY').box(12,6,d,centered=(True,True,False)).translate((sign*64,8,0)))
        front=front.cut(cq.Workplane('XY').center(sign*p['hinge_x'],8).circle(.9).extrude(d))
    w,h,l,wall=p['temple_width'],p['temple_height'],p['temple_length'],p['temple_wall'];bay=p['electronics_bay_length']
    if w-2*wall < p['battery_cell_thickness']+p['battery_clearance']:raise ValueError('battery thickness does not fit')
    if h-2*wall < 18+0.6:raise ValueError('WROOM module height does not fit')
    temple=cq.Workplane('XY').box(w,h,bay,centered=(True,True,False))
    temple=temple.union(cq.Workplane('XY').box(5,7,l-bay,centered=(True,True,False)).translate((0,0,bay)))
    cavity=cq.Workplane('XY').box(w-2*wall,h,bay-8,centered=(True,True,False)).translate((0,wall,4))
    temple=temple.cut(cavity)
    # The lid sits OUTSIDE the shell. Raised end seats carry screw preload;
    # the 0.2 mm side gap is a fixture clearance, not an environmental seal.
    for z in [0,bay-p['cover_seat_length']]:
        seat=cq.Workplane('XY').box(w,p['cover_gap'],p['cover_seat_length'],centered=(True,True,False))
        temple=temple.union(seat.translate((0,h/2+p['cover_gap']/2,z)))
    cover=cq.Workplane('XY').box(w,wall,bay,centered=(True,True,False))
    for z in [2,bay-2]:
        hole=cq.Workplane('XZ').center(0,z).circle(.7).extrude(h+2,both=True)
        temple=temple.cut(hole)
        cover=cover.cut(cq.Workplane('XZ').center(0,z).circle(.9).extrude(3,both=True))
    return {'front':front,'temple':temple,'cover':cover}


def placement(p, sign, cover=False):
    return (sign*p['hinge_x'],8+(p['temple_height']/2+p['cover_gap']+p['temple_wall']/2 if cover else 0),p['front_depth'])


def build():
    p=json.loads((ROOT/'hardware/mechanical/parameters.json').read_text());parts=geometry(p)
    front,temple,cover=(parts[name] for name in ['front','temple','cover'])
    assembly=cq.Assembly(name='AgentGlass_H1_PACKAGING_FIXTURE')
    assembly.add(front,name='front',color=cq.Color(.12,.15,.18))
    for sign,name in [(-1,'left_temple'),(1,'right_temple')]:
        assembly.add(temple,name=name,loc=cq.Location(cq.Vector(*placement(p,sign))),color=cq.Color(.15,.17,.2))
        assembly.add(cover,name=name+'_cover',loc=cq.Location(cq.Vector(*placement(p,sign,True))),color=cq.Color(.25,.28,.31))
    optic=cq.Workplane('XY').box(*p['optical_envelope'],centered=(False,False,False)).translate((-44,13,4))
    assembly.add(optic,name='RFQ_ONLY_optic_envelope',color=cq.Color(.2,.7,.4,.4))
    out=ROOT/'hardware/mechanical/generated';out.mkdir(exist_ok=True)
    assembly.save(str(out/'agentglass-h1-fixture.step'))
    volumes={}
    for name,shape in parts.items():
        if not shape.val().isValid():raise ValueError(name+' invalid BREP')
        cq.exporters.export(shape,str(out/(name+'.stl')))
        cq.exporters.export(shape,str(out/(name+'.step')))
        volumes[name]=round(sum(s.Volume() for s in shape.solids().vals()),3)
    report={'evidence_level':2,'brep_valid':True,'fixture_volume_mm3':volumes,
            'PA12_1_01g_cm3_shell_estimate_g':round((volumes['temple']+volumes['cover'])*1.01/1000,3),
            'note':'Geometry generation only. Shell volume is not the product mass budget. Frame/lens retention, hinge mechanism, ergonomic fit and final engine mounting are not released.'}
    (ROOT/'docs/evidence/cad-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':build()
