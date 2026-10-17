#pragma once
#include <stdint.h>
// Render a 128x64 monochrome HUD in the 126x126 visible prism region.
// Both source edges survive resampling. RGB565 white avoids byte-order ambiguity.
inline void expandHud126(const uint8_t source[1024],uint16_t target[126*126]){
  for(unsigned y=0;y<126;y++)for(unsigned x=0;x<126;x++){
    unsigned sx=(x*127+62)/125;
    bool lit=y>=31&&y<95&&(source[(y-31)*16+sx/8]&(1u<<(7-sx%8)));
    target[y*126+x]=lit?0xffff:0;
  }
}
