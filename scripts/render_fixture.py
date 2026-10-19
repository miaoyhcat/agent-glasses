#!/usr/bin/env python3
"""Render the real generated CAD shapes; green block is an RFQ envelope only."""
import json
from pathlib import Path
import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from build_cad import placement

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=json.loads((ROOT/'hardware/mechanical/parameters.json').read_text());g=ROOT/'hardware/mechanical/generated'
    fig=plt.figure(figsize=(12,7),facecolor='#f4f6f8');ax=fig.add_subplot(111,projection='3d',facecolor='#f4f6f8')
    def add(shape,color,alpha=1):
        vertices,faces=shape.tessellate(.5,.2)
        # Render rearward z as plot y, vertical CAD y as plot z.
        xyz=[(v.x,v.z,v.y) for v in vertices]
        mesh=Poly3DCollection([[xyz[i] for i in face] for face in faces],facecolor=color,edgecolor='none',alpha=alpha)
        ax.add_collection3d(mesh)
    front=cq.importers.importStep(str(g/'front.step')).val();add(front,'#33404c')
    temple=cq.importers.importStep(str(g/'temple.step')).val();cover=cq.importers.importStep(str(g/'cover.step')).val()
    for sign in [-1,1]:
        add(temple.translate(placement(p,sign)),'#46545f')
        add(cover.translate(placement(p,sign,True)),'#647681')
    optic=cq.Workplane('XY').box(*p['optical_envelope'],centered=(False,False,False)).translate((-44,13,4)).val();add(optic,'#2eaf83',.6)
    ax.set(xlim=(-90,90),ylim=(-20,155),zlim=(-35,45),xlabel='left / right (mm)',ylabel='rearward (mm)',zlabel='')
    ax.set_box_aspect((180,175,80));ax.view_init(elev=26,azim=-58);ax.grid(False)
    fig.suptitle('CodexGlasses H1 | CAD packaging fixture',x=.08,ha='left',fontsize=21,fontweight='bold',color='#23323e')
    fig.text(.08,.875,'Green: unconfirmed optical-engine envelope. No powered prototype or finished frame.',fontsize=11,color='#53616c')
    fig.text(.08,.045,'Generated from delivered STEP geometry. Hinge mechanism, lens retention and supplier mounting remain unresolved.',fontsize=10,color='#53616c')
    (ROOT/'assets').mkdir(exist_ok=True);fig.savefig(ROOT/'assets/packaging-fixture.png',dpi=140,bbox_inches='tight');plt.close(fig)


if __name__=='__main__':main()
