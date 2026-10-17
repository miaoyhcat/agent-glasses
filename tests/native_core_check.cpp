#include "media_id.h"
#include "hud_raster.h"
#include <cstdio>
#include <cstring>
#include <cstdint>
int main(){
 uint8_t input[16];char id[27];
 for(unsigned n=0;n<256;n++){
  for(unsigned i=0;i<16;i++)input[i]=(uint8_t)(n+i*17);
  encodeMediaId(input,id);if(std::strlen(id)!=26)return 1;
  std::puts(id);
 }
 uint8_t pixels[1024]={};uint16_t guarded[126*126+2];guarded[0]=0x1234;guarded[126*126+1]=0x5678;
 expandHud126(pixels,guarded+1);for(unsigned i=1;i<=126*126;i++)if(guarded[i])return 2;
 std::memset(pixels,255,sizeof(pixels));expandHud126(pixels,guarded+1);
 for(unsigned y=0;y<126;y++)for(unsigned x=0;x<126;x++)if(guarded[1+y*126+x]!=(y>=31&&y<95?0xffff:0))return 3;
 std::memset(pixels,0,sizeof(pixels));pixels[0]=0x80;pixels[15]=1;expandHud126(pixels,guarded+1);
 if(guarded[1+31*126]!=0xffff||guarded[1+31*126+125]!=0xffff)return 4;
 if(guarded[0]!=0x1234||guarded[126*126+1]!=0x5678)return 5;
 std::puts("PASS actual firmware raster: black, white, letterbox, both edges, bounds");
}
