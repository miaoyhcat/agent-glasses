// Editable H1 packaging fixture. Unit mm. Geometry is not a qualified eyewear frame.
$fn=64;
part="assembly"; // [assembly,front,left_temple,right_temple,cover]
rim_rx=27; rim_ry=20; lens_rx=23.5; lens_ry=16.5; center_x=35;
front_depth=3.5; hinge_x=68; temple_length=145; temple_w=8.6; temple_h=20.4; wall=.8; bay=65; cover_gap=.2; seat=4;
module ring(){linear_extrude(height=front_depth)difference(){scale([rim_rx,rim_ry])circle(1);scale([lens_rx,lens_ry])circle(1);}}
module front(){difference(){union(){for(s=[-1,1]){translate([s*center_x,0,0])ring();translate([s*64-6,5,0])cube([12,6,front_depth]);}translate([-10,7,0])cube([20,5,front_depth]);}
for(s=[-1,1])translate([s*hinge_x,8,0])cylinder(h=front_depth,r=.9);}}
module temple(){difference(){union(){difference(){union(){translate([-temple_w/2,-temple_h/2,0])cube([temple_w,temple_h,bay]);translate([-2.5,-3.5,bay])cube([5,7,temple_length-bay]);}translate([-temple_w/2+wall,-temple_h/2+wall,4])cube([temple_w-2*wall,temple_h,bay-8]);}for(z=[0,bay-seat])translate([-temple_w/2,temple_h/2,z])cube([temple_w,cover_gap,seat]);}
for(z=[2,bay-2])translate([0,0,z])rotate([90,0,0])cylinder(h=temple_h+2,r=.7,center=true);}}
module cover(){difference(){translate([-temple_w/2,-wall/2,0])cube([temple_w,wall,bay]);for(z=[2,bay-2])translate([0,0,z])rotate([90,0,0])cylinder(h=3,r=.9,center=true);}}
if(part=="front")front();else if(part=="left_temple"||part=="right_temple")temple();else if(part=="cover")cover();else{
 color([.12,.15,.18])front();for(s=[-1,1]){
 translate([s*hinge_x,8,front_depth])color([.15,.17,.2])temple();
 translate([s*hinge_x,8+temple_h/2+cover_gap+wall/2,front_depth])color([.25,.28,.31])cover();}
 for(s=[-1,1])translate([s*center_x,0,1])color([.6,.85,1,.18])linear_extrude(1.5)scale([lens_rx,lens_ry])circle(1);
 // Supplier optical envelope only: replace with signed mechanical drawing before layout release.
 translate([-44,13,4])color([.2,.7,.4,.6])cube([18,15,14]);
}
