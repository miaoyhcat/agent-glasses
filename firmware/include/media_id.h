#pragma once
#include <stdint.h>
// 128 random bits -> 26 lowercase RFC4648 base32 characters + NUL.
// Longest final SPIFFS path: '/' + 26 + '.jpg' + NUL = 32 bytes.
// Temporary paths use '.p', not a suffix appended to the final extension.
inline void encodeMediaId(const uint8_t input[16],char output[27]){
  static const char alphabet[]="abcdefghijklmnopqrstuvwxyz234567";
  uint32_t bits=0;unsigned count=0,index=0;
  for(unsigned i=0;i<16;i++){
    bits=(bits<<8)|input[i];count+=8;
    while(count>=5){count-=5;output[index++]=alphabet[(bits>>count)&31];}
  }
  if(count)output[index++]=alphabet[(bits<<(5-count))&31];
  output[index]=0;
}
