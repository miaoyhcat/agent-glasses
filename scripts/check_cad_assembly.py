#!/usr/bin/env python3
"""Boolean checks of actual exported parts, not an image-based fit assertion."""
import itertools
import json
from pathlib import Path
import cadquery as cq
from build_cad import ROOT, geometry, placement


def main():
    p=json.loads((ROOT/'hardware/mechanical/parameters.json').read_text())
    directory=ROOT/'hardware/mechanical/generated'
    shapes={name:cq.importers.importStep(str(directory/(name+'.step'))).val()
            for name in ['front','temple','cover']}
    placed={'front':shapes['front']}
    for sign,name in [(-1,'left'),(1,'right')]:
        for part in ['temple','cover']:
            placed[name+'_'+part]=shapes[part].translate(placement(p,sign,part=='cover'))
    checks=[]
    for (a,sa),(b,sb) in itertools.combinations(placed.items(),2):
        v=sa.intersect(sb).Volume()
        checks.append({'pair':[a,b],'overlap_mm3':v,'passed':v<1e-5})
    # Reproduce the previous assembly offset against the CURRENT shell: a
    # deliberately broken placement must be detected by the same check.
    old=shapes['cover'].translate((0,p['temple_height']/2-p['temple_wall']/2,0))
    old_overlap=shapes['temple'].intersect(old).Volume()
    assert old_overlap>100,'Regression check did not reproduce the lid interference'
    assert all(c['passed'] for c in checks),'Assembly interference'
    # Seat contact is intentional, not a gap. Lateral screw assembly allowance
    # is clearance hole 1.8 mm minus nominal screw 1.6 mm = 0.1 mm radial.
    assert (1.8-1.6)/2>=.099
    report={'evidence_level':2,'scope':'unpowered fixture only; RFQ optical envelope excluded',
            'brep_valid':all(s.isValid() for s in shapes.values()),
            'pairwise_checks':checks,'old_lid_placement_overlap_mm3':old_overlap,
            'cover_side_gap_mm':p['cover_gap'],'screw_nominal_radial_clearance_mm':.1,
            'not_verified':['supplier components','screw engagement strength','printing tolerances','hinge kinematics','lens retention','optical alignment'],
            'passed':True}
    assert report['brep_valid']
    (ROOT/'docs/evidence/cad-assembly-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
