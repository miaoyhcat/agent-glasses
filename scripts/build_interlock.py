#!/usr/bin/env python3
"""Generate a real KiCad 7 low-voltage interlock TEST COUPON, not the H1 main PCB.

Uses pcbnew and a conservative two-layer grid router. Schematic and PCB share
one net definition. Exact component package geometry must still be reviewed.
"""
import csv
import heapq
import json
import math
import uuid
from pathlib import Path
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/pcb/interlock-test-coupon'
GRID=.25
WIDTH,HEIGHT=70,45

# Standard DIP8 dual comparator pinout; TPS22918 DBV pins from TI table 5.
PARTS=[
 ('J1','3V3_IN','header',8,8,['VIN','GND']),
 ('SW1','EXTERNAL_MASTER_SWITCH','header',8,20,['VIN','VSW']),
 ('J2','MCU_CTRL','header',8,33,['REQ','GND','VSW']),
 ('J3','CAMERA_3V3_OUT','header',62,32,['VCAM','GND']),
 ('U1','MCP6547-I/P','dip8',31,23,['EN','VLOW','LED','GND','VHIGH','LED','EN','VSW']),
 ('U2','TPS22918DBVR','sot6',50,20,['VSW','GND','EN','CT','VCAM','VCAM']),
 ('R1','330','r',22,10,['REQ','LED']),
 ('D1','VISIBLE_GREEN_LED','led',32,10,['GND','LED']),
 ('R2','232k 1%','r',20,20,['VSW','VLOW']),
 ('R3','100k 1%','r',20,26,['VLOW','GND']),
 ('R4','22.1k 1%','r',40,30,['VSW','VHIGH']),
 ('R5','100k 1%','r',40,36,['VHIGH','GND']),
 ('R6','10k','r',20,36,['REQ','EN']),
 ('R7','100k','r',30,36,['EN','GND']),
 ('C1','1uF','c',43,10,['VSW','GND']),
 ('C2','1uF','c',60,20,['VCAM','GND']),
 ('C3','1nF','c',51,28,['CT','GND']),
 ('C4','100nF','c',31,30,['VSW','GND'])]


def point(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def gridpoint(x,y):return (round(x/GRID),round(y/GRID))
def layer_set(*layers):
    result=k.LSET()
    for layer in layers:result.AddLayer(layer)
    return result


def footprint(ref,value,kind,x,y,nets,board,netcodes):
    fp=k.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value);fp.SetPosition(point(x,y))
    fp.Reference().SetPosition(point(x,y-3));fp.Reference().SetTextSize(point(.8,.8));fp.Reference().SetTextThickness(k.FromMM(.12))
    fp.Value().SetVisible(False)
    if kind=='header':coords=[(0,i*2.54) for i in range(len(nets))];size=(1.7,1.7);drill=.9
    elif kind=='dip8':coords=[(-3.81,-3.81+i*2.54) for i in range(4)]+[(3.81,3.81-i*2.54) for i in range(4)];size=(1.8,1.8);drill=.8
    elif kind=='sot6':coords=[(-1.1,-.95),(-1.1,0),(-1.1,.95),(1.1,.95),(1.1,0),(1.1,-.95)];size=(1.0,.6);drill=0
    else:coords=[(-1.0,0),(1.0,0)];size=(1.1,1.3);drill=0
    pads=[]
    for i,((dx,dy),net) in enumerate(zip(coords,nets),1):
        pad=k.PAD(fp);pad.SetNumber(str(i));pad.SetPosition(point(x+dx,y+dy));pad.SetSize(point(*size));pad.SetNet(netcodes[net])
        if drill:
            pad.SetAttribute(k.PAD_ATTRIB_PTH);pad.SetDrillSize(point(drill,drill));pad.SetShape(k.PAD_SHAPE_CIRCLE);pad.SetLayerSet(layer_set(k.F_Cu,k.B_Cu,k.F_Mask,k.B_Mask))
        else:
            pad.SetAttribute(k.PAD_ATTRIB_SMD);pad.SetShape(k.PAD_SHAPE_RECT);pad.SetLayerSet(layer_set(k.F_Cu,k.F_Paste,k.F_Mask))
        fp.Add(pad);pad.SetPos0(point(dx,dy));pad.SetPosition(point(x+dx,y+dy))
        pads.append({'ref':ref,'pin':i,'net':net,'x':x+dx,'y':y+dy,'w':size[0],'h':size[1],'through':bool(drill)})
    board.Add(fp);return pads


def generate_schematic():
    schematic=ROOT/'hardware/schematics';schematic.mkdir(exist_ok=True)
    for obsolete in ['interlock-cache.lib','interlock.sch']:
        (schematic/obsolete).unlink(missing_ok=True)
    generate_modern_schematic(schematic)


def generate_modern_schematic(directory):
    def uid():return str(uuid.uuid4())
    def quoted(s):return json.dumps(s)
    def effect(size=1.0):return f'(effects (font (size {size} {size})))'
    root=uid();symbols=[];instances=[];wires=[]
    for idx,(ref,value,kind,x,y,nets) in enumerate(PARTS):
        name='PART_'+ref;half=max(2.54,len(nets)*1.27);sx=30+(idx%4)*90;sy=30+(idx//4)*50
        lib=[f'(symbol "AgentGlass:{name}" (pin_names (offset 0.5)) (in_bom yes) (on_board yes)',
             f'(property "Reference" "{ref.rstrip("0123456789")}" (at 0 {half+2.5} 0) {effect()})',
             f'(property "Value" {quoted(value)} (at 0 {-half-2.5} 0) {effect()})',
             f'(symbol "{name}_0_1" (rectangle (start -7.62 {half}) (end 7.62 {-half}) (stroke (width .254) (type default)) (fill (type background))))',
             f'(symbol "{name}_1_1"']
        ins=[f'(symbol (lib_id "AgentGlass:{name}") (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (uuid {uid()})',
             f'(property "Reference" "{ref}" (at {sx} {sy-half-2.5} 0) {effect()})',
             f'(property "Value" {quoted(value)} (at {sx} {sy+half+2.5} 0) {effect(.85)})']
        for i,net in enumerate(nets,1):
            py=half-i*2.54+1.27
            lib.append(f'(pin passive line (at -10.16 {py} 0) (length 2.54) (name "{net}" {effect(.85)}) (number "{i}" {effect(.85)}))')
            ins.append(f'(pin "{i}" (uuid {uid()}))')
            ay=sy-py
            wires.append(f'(wire (pts (xy {sx-18} {ay}) (xy {sx-10.16} {ay})) (stroke (width 0) (type default)) (uuid {uid()}))')
            wires.append(f'(label "{net}" (at {sx-18} {ay} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {uid()}))')
        lib.extend(['))']);symbols.append('\n'.join(lib))
        ins.append(f'(instances (project "interlock" (path "/{root}" (reference "{ref}") (unit 1)))))');instances.append('\n'.join(ins))
    content=f'(kicad_sch (version 20230121) (generator eeschema) (uuid {root}) (paper "A3")\n(lib_symbols\n'+ '\n'.join(symbols)+')\n'+'\n'.join(wires+instances)+'\n(sheet_instances (path "/" (page "1"))))\n'
    (directory/'interlock.kicad_sch').write_text(content)


def build():
    OUT.mkdir(parents=True,exist_ok=True);board=k.BOARD()
    netnames=sorted(set(n for p in PARTS for n in p[-1]));netcodes={}
    for name in netnames:
        net=k.NETINFO_ITEM(board,name);board.Add(net);netcodes[name]=net
    pads=[]
    for part in PARTS:pads+=footprint(*part,board,netcodes)
    for a,b in [((2,2),(68,2)),((68,2),(68,43)),((68,43),(2,43)),((2,43),(2,2))]:
        edge=k.PCB_SHAPE();edge.SetShape(k.SHAPE_T_SEGMENT);edge.SetStart(point(*a));edge.SetEnd(point(*b));edge.SetLayer(k.Edge_Cuts);edge.SetWidth(k.FromMM(.05));board.Add(edge)
    traces=[];vias=[]
    def blocked_for(net):
        blocked=[set(),set()]
        def rect(layer,x0,y0,x1,y1):
            for ix in range(math.floor(x0/GRID),math.ceil(x1/GRID)+1):
                for iy in range(math.floor(y0/GRID),math.ceil(y1/GRID)+1):blocked[layer].add((ix,iy))
        clearance=.36
        for p in pads:
            if p['net']==net:continue
            for layer in ([0,1] if p['through'] else [0]):rect(layer,p['x']-p['w']/2-clearance,p['y']-p['h']/2-clearance,p['x']+p['w']/2+clearance,p['y']+p['h']/2+clearance)
        for layer,x1,y1,x2,y2,other in traces:
            if other==net:continue
            rect(layer,min(x1,x2)-.51,min(y1,y2)-.51,max(x1,x2)+.51,max(y1,y2)+.51)
        for x,y,other in vias:
            if other==net:continue
            for layer in [0,1]:rect(layer,x-.66,y-.66,x+.66,y+.66)
        return blocked
    def route(net,start,goal):
        blocked=blocked_for(net);s=(*gridpoint(start['x'],start['y']),0);g=(*gridpoint(goal['x'],goal['y']),0)
        heap=[(0,0,s)];cost={s:0};previous={};visited=0
        while heap:
            _,distance,current=heapq.heappop(heap)
            if distance!=cost[current]:continue
            if current==g:
                path=[g]
                while path[-1]!=s:path.append(previous[path[-1]])
                return list(reversed(path))
            visited+=1
            if visited>300000:break
            x,y,layer=current
            for nx,ny,nl,weight in [(x+1,y,layer,1),(x-1,y,layer,1),(x,y+1,layer,1),(x,y-1,layer,1),(x,y,1-layer,16)]:
                nxt=(nx,ny,nl)
                if not (12<=nx<268 and 12<=ny<168) or (nx,ny) in blocked[nl]:continue
                if nl!=layer:
                    if any((nx+dx,ny+dy) in blocked[a] for a in [0,1] for dx in [-1,0,1] for dy in [-1,0,1]):continue
                    near_hole=False
                    for p in pads:
                        if p['through']:
                            distance_to_pad=math.hypot(nx*GRID-p['x'],ny*GRID-p['y'])
                            if distance_to_pad<1.0 and not (p['net']==net and distance_to_pad<.7):near_hole=True
                    if near_hole:continue
                updated=distance+weight
                if updated<cost.get(nxt,1e30):
                    cost[nxt]=updated;previous[nxt]=current;heuristic=abs(nx-g[0])+abs(ny-g[1])+(0 if nl==g[2] else 8)
                    heapq.heappush(heap,(updated+heuristic,updated,nxt))
        raise RuntimeError('routing_failed:'+net)
    for name in [n for n in netnames if n!='GND']:
        nodes=[p for p in pads if p['net']==name];connected=[nodes.pop(0)]
        while nodes:
            _,a,b=min(((abs(a['x']-b['x'])+abs(a['y']-b['y']),a,b) for a in connected for b in nodes),key=lambda item:item[0])
            path=route(name,a,b)
            coordinates=[(a['x'],a['y'],0)]+[(x*GRID,y*GRID,l) for x,y,l in path]+[(b['x'],b['y'],0)]
            for first,second in zip(coordinates,coordinates[1:]):
                x1,y1,layer=first;x2,y2,nl=second
                if nl!=layer:
                    if any(p['through'] and p['net']==name and math.hypot(x1-p['x'],y1-p['y'])<.7 for p in pads):
                        continue  # The existing PTH barrel already connects the two copper layers.
                    via=k.PCB_VIA(board);via.SetPosition(point(x1,y1));via.SetWidth(k.FromMM(.6));via.SetDrill(k.FromMM(.3));via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(netcodes[name].GetNetCode());board.Add(via);vias.append((x1,y1,name))
                elif abs(x1-x2)+abs(y1-y2)>1e-6:
                    track=k.PCB_TRACK(board);track.SetStart(point(x1,y1));track.SetEnd(point(x2,y2));track.SetLayer(k.F_Cu if layer==0 else k.B_Cu);track.SetWidth(k.FromMM(.3));track.SetNetCode(netcodes[name].GetNetCode());board.Add(track);traces.append((layer,x1,y1,x2,y2,name))
            connected.append(b);nodes.remove(b)
    for layer in [k.F_Cu,k.B_Cu]:
        zone=k.ZONE(board);zone.SetLayer(layer);zone.SetNetCode(netcodes['GND'].GetNetCode());zone.SetLocalClearance(k.FromMM(.25));zone.SetThermalReliefGap(k.FromMM(.25));zone.SetThermalReliefSpokeWidth(k.FromMM(.3))
        poly=zone.Outline();poly.NewOutline()
        for x,y in [(2.5,2.5),(67.5,2.5),(67.5,42.5),(2.5,42.5)]:poly.Append(int(k.FromMM(x)),int(k.FromMM(y)))
        board.Add(zone)
    # Dedicated return for the small SOT23 ground pad; avoids relying on a narrow thermal island.
    ground=k.PCB_TRACK(board);ground.SetStart(point(48.9,20));ground.SetEnd(point(47.5,20));ground.SetWidth(k.FromMM(.3));ground.SetLayer(k.F_Cu);ground.SetNetCode(netcodes['GND'].GetNetCode());board.Add(ground)
    via=k.PCB_VIA(board);via.SetPosition(point(47.5,20));via.SetWidth(k.FromMM(.6));via.SetDrill(k.FromMM(.3));via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(netcodes['GND'].GetNetCode());board.Add(via)
    text=k.PCB_TEXT(board);text.SetText('AgentGlass LED interlock TEST ONLY / 3.3V');text.SetPosition(point(35,41));text.SetTextSize(point(.8,.8));text.SetTextThickness(k.FromMM(.12));text.SetLayer(k.F_SilkS);board.Add(text)
    board.BuildConnectivity()
    file=OUT/'interlock-test.kicad_pcb';k.SaveBoard(str(file),board)
    # Round-trip initializes KiCad's board design settings/net-class caches.
    loaded=k.LoadBoard(str(file));loaded.BuildConnectivity()
    filler=k.ZONE_FILLER(loaded);filler.Fill(loaded.Zones());k.SaveBoard(str(file),loaded)
    generate_schematic()
    with (OUT/'connections.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['ref','pin','net','x','y','w','h','through']);writer.writeheader();writer.writerows(pads)
    report={'type':'3.3V interlock test coupon only','components':len(PARTS),'nets':len(netnames),
      'track_segments':sum(t.GetClass()=='PCB_TRACK' for t in loaded.GetTracks()),'vias':sum(t.GetClass()=='PCB_VIA' for t in loaded.GetTracks()),
      'manufacturing_release':False,'note':'A generated routed coupon is not a validated camera safety system. DRC, netlist reconciliation and electrical fault injection are separate gates.'}
    (ROOT/'docs/evidence/interlock-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':build()
