// AgentGlass P1: procurement-first near-eye HUD on a complete LILYGO T-Glass V2.
// Display-only target: camera/audio/storage remain on D0/phone. Not H1 optics.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <NimBLEDevice.h>
#include <LilyGo_Wristband.h>
#include <mbedtls/md.h>
#include <mbedtls/base64.h>
#include <sys/time.h>
#include "hud_raster.h"
static Preferences prefs;
static LilyGo_Class optic;
static uint8_t keyBytes[32];static bool provisioned=false,clockValid=false;
static volatile bool bleAuthenticated=false;static volatile uint16_t bleHandle=0xffff;
static int timezoneMinutes=0;static uint64_t lastSeq=0;
static String sessionId,serialLine,bleLine;
static NimBLECharacteristic* tx=nullptr;static QueueHandle_t commands;static SemaphoreHandle_t sendMutex;
static uint32_t lastHudAt=0,lastClockAt=0;
static const char* SERVICE="6e400001-b5a3-f393-e0a9-e50e24dcca9e";
static const char* RX_UUID="6e400002-b5a3-f393-e0a9-e50e24dcca9e";
static const char* TX_UUID="6e400003-b5a3-f393-e0a9-e50e24dcca9e";
static uint16_t raster[126*126];
bool drawBitmap(const String& encoded){
 uint8_t source[1024];size_t n=0;
 if(mbedtls_base64_decode(source,sizeof(source),&n,(const uint8_t*)encoded.c_str(),encoded.length())||n!=1024)return false;
 expandHud126(source,raster);
 // Use explicit address-window + BYTE count. The upstream x/y pushColors
 // wrapper passes width/height into an end-coordinate API and is not used.
 optic.setAddrWindow(0,168,126,126);optic.pushColors(raster,sizeof(raster));
 delay(12); // DMA transfer margin at vendor's 70MHz; validate on a physical board.
 return true;
}
String hexBytes(const uint8_t* data,size_t length){
  static const char* digits="0123456789abcdef";String out;out.reserve(length*2);
  for(size_t i=0;i<length;i++){out+=digits[data[i]>>4];out+=digits[data[i]&15];}return out;
}
bool decodeHex(const String& in,uint8_t* out,size_t n){
  if(in.length()!=n*2)return false;
  for(size_t i=0;i<n;i++){char a=in[i*2],b=in[i*2+1];
    if(!isxdigit(a)||!isxdigit(b))return false;
    out[i]=strtoul(in.substring(i*2,i*2+2).c_str(),nullptr,16);
  }return true;
}
void emit(JsonDocument& message){
  String out;serializeJson(message,out);out+='\n';
  xSemaphoreTake(sendMutex,portMAX_DELAY);
  Serial.print(out);
  if(tx&&bleAuthenticated&&NimBLEDevice::getServer()->getConnectedCount()){
    uint16_t mtu=NimBLEDevice::getServer()->getPeerMTU(bleHandle);size_t payload=mtu>23?min((size_t)180,(size_t)mtu-3):20;
    for(size_t i=0;i<out.length();i+=payload){
      tx->setValue((uint8_t*)out.c_str()+i,min(payload,out.length()-i));tx->notify();delay(8);
    }
  }xSemaphoreGive(sendMutex);
}
void error(const char* code){StaticJsonDocument<192> j;j["v"]=1;j["type"]="error";j["code"]=code;emit(j);}
void hello(){StaticJsonDocument<256> j;j["v"]=1;j["type"]="hello";j["session"]=sessionId;
  j["profile"]="TGLASS_V2_NEAR_EYE";j["provisioned"]=provisioned;j["media_link_encrypted"]=true;emit(j);
  if(tx){String readable;serializeJson(j,readable);readable+='\n';tx->setValue(readable.c_str());}}

void drawClock(){
  static const uint8_t glyph[10][5]={{0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},{0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},{0x36,0x49,0x49,0x49,0x36},{6,0x49,0x49,0x29,0x1e}};
  char text[6]="--:--";
  if(clockValid){time_t now=time(nullptr)+timezoneMinutes*60;struct tm tm;gmtime_r(&now,&tm);snprintf(text,sizeof(text),"%02d:%02d",tm.tm_hour,tm.tm_min);}
  uint8_t bitmap[1024]={};
  auto pixel=[&](int x,int y){if(x>=0&&x<128&&y>=0&&y<64)bitmap[y*16+x/8]|=1<<(7-x%8);};
  int x=19;
  for(char c:text){if(c==0)break;
    for(int col=0;col<5;col++)for(int row=0;row<7;row++){
      bool lit=(c>='0'&&c<='9')?(glyph[c-'0'][col]&(1<<row)):(c==':'?(col==2&&(row==2||row==4)):(row==3));
      if(lit)for(int dx=0;dx<3;dx++)for(int dy=0;dy<3;dy++)pixel(x+col*3+dx,20+row*3+dy);
    }x+=18;
  }
  uint8_t encoded[1400];size_t n=0;mbedtls_base64_encode(encoded,sizeof(encoded),&n,bitmap,sizeof(bitmap));drawBitmap(String((char*)encoded,n));
}

bool authenticate(JsonDocument& frame,JsonDocument& body){
  if(!provisioned||frame["v"]!=1||!frame["seq"].is<uint64_t>()||!frame["body"].is<const char*>()||!frame["mac"].is<const char*>())return false;
  uint64_t seq=frame["seq"].as<uint64_t>();if(seq<=lastSeq)return false;
  String payload=frame["body"].as<String>(),mac=frame["mac"].as<String>();
  char decimal[24];snprintf(decimal,sizeof(decimal),"%llu",(unsigned long long)seq);
  String message=sessionId+"\n"+decimal+"\n"+payload;uint8_t expected[32],provided[32];
  if(!decodeHex(mac,provided,32))return false;
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),keyBytes,32,(const uint8_t*)message.c_str(),message.length(),expected);
  uint8_t mismatch=0;for(int i=0;i<32;i++)mismatch|=expected[i]^provided[i];if(mismatch)return false;
  lastSeq=seq;return !deserializeJson(body,payload);
}
void execute(const String& line){
 DynamicJsonDocument frame(5000),body(3500);
 if(deserializeJson(frame,line)||!authenticate(frame,body)){error("authentication_or_frame_failed");return;}
 String op=body["op"]|"";
 if(op=="hud"){
  if(!body["bitmap"].is<const char*>()||!drawBitmap(body["bitmap"].as<String>())){error("bitmap_128x64_required");return;}lastHudAt=millis();
 }else if(op=="status"){
  if(body["unix"].is<uint64_t>()){
   uint64_t epoch=body["unix"].as<uint64_t>();int zone=body["tz_minutes"]|0;
   if(epoch<1577836800ULL||epoch>2145916800ULL||zone<-840||zone>840){error("invalid_time");return;}
   struct timeval value={(time_t)epoch,0};settimeofday(&value,nullptr);timezoneMinutes=zone;clockValid=true;
  }
 }else{error("display_only_profile");return;}
 StaticJsonDocument<192> reply;reply["v"]=1;reply["type"]="status";reply["profile"]="TGLASS_V2_NEAR_EYE";reply["last_seq"]=lastSeq;reply["battery_percent"]=nullptr;emit(reply);
}
void enqueue(String& line){
  if(line.length()&&line.length()<4096){char* command=(char*)malloc(line.length()+1);if(command){strcpy(command,line.c_str());if(xQueueSend(commands,&command,0)!=pdTRUE){free(command);error("command_queue_full");}}}
  line="";
}
class RXCallbacks:public NimBLECharacteristicCallbacks{
  void onWrite(NimBLECharacteristic* c)override{
    std::string value=c->getValue();for(char ch:value){if(ch=='\n')enqueue(bleLine);else if(ch!='\r'){bleLine+=ch;if(bleLine.length()>=4096){bleLine="";error("frame_too_large");}}}
  }
};
class ServerCallbacks:public NimBLEServerCallbacks{
  void onConnect(NimBLEServer* s,ble_gap_conn_desc* desc)override{bleHandle=desc->conn_handle;NimBLEDevice::startSecurity(desc->conn_handle);}
  void onDisconnect(NimBLEServer* s)override{bleAuthenticated=false;bleHandle=0xffff;bleLine="";NimBLEDevice::startAdvertising();}
  void onAuthenticationComplete(ble_gap_conn_desc* desc)override{
    if(!desc->sec_state.encrypted||!desc->sec_state.authenticated){NimBLEDevice::getServer()->disconnect(desc->conn_handle);return;}bleAuthenticated=true;hello();
  }
};
void setup(){
  Serial.begin(115200);sendMutex=xSemaphoreCreateMutex();commands=xQueueCreate(4,sizeof(char*));
  pinMode(BOARD_BOOT_PIN,INPUT_PULLUP);
  if(!optic.begin()){Serial.println("display initialization failed");while(true)delay(1000);}
  optic.setRotation(0);optic.setBrightness(16);
  static uint16_t blank[126]={};
  for(int y=0;y<294;y++){optic.setAddrWindow(0,y,126,1);optic.pushColors(blank,sizeof(blank));delay(1);}
  uint8_t randomSession[16];esp_fill_random(randomSession,16);sessionId=hexBytes(randomSession,16);
  prefs.begin("agentglass",false);provisioned=prefs.getBytesLength("key")==32;if(provisioned)prefs.getBytes("key",keyBytes,32);
  drawClock();
  // Pairing passkey is shown on USB console; D0 has no font renderer.
  uint32_t passkey=100000+(esp_random()%900000);Serial.printf("BLE pairing passkey: %06lu\n",(unsigned long)passkey);
  NimBLEDevice::init("AgentGlass-TGlass-V2");NimBLEDevice::setMTU(247);NimBLEDevice::setSecurityAuth(true,true,true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);NimBLEDevice::setSecurityPasskey(passkey);
  NimBLEServer* s=NimBLEDevice::createServer();s->setCallbacks(new ServerCallbacks());
  NimBLEService* service=s->createService(SERVICE);
  tx=service->createCharacteristic(TX_UUID,NIMBLE_PROPERTY::READ|NIMBLE_PROPERTY::NOTIFY|NIMBLE_PROPERTY::READ_ENC|NIMBLE_PROPERTY::READ_AUTHEN);
  auto rx=service->createCharacteristic(RX_UUID,NIMBLE_PROPERTY::WRITE|NIMBLE_PROPERTY::WRITE_ENC|NIMBLE_PROPERTY::WRITE_AUTHEN);
  rx->setCallbacks(new RXCallbacks());service->start();auto advertising=NimBLEDevice::getAdvertising();advertising->addServiceUUID(SERVICE);advertising->start();hello();
}
void loop(){
 while(Serial.available()){
  char c=Serial.read();if(c=='\n'){
   if(serialLine.startsWith("provision ")&&digitalRead(BOARD_BOOT_PIN)==LOW){
    uint8_t next[32];if(decodeHex(serialLine.substring(10),next,32)){
     prefs.putBytes("key",next,32);memcpy(keyBytes,next,32);provisioned=true;lastSeq=0;
     esp_fill_random(next,16);sessionId=hexBytes(next,16);hello();
    }else error("invalid_key");serialLine="";
   }else enqueue(serialLine);
  }else if(c!='\r'){serialLine+=c;if(serialLine.length()>=4096){serialLine="";error("frame_too_large");}}
 }
 char* command=nullptr;if(xQueueReceive(commands,&command,0)==pdTRUE){execute(String(command));free(command);}
 if(millis()-lastHudAt>3500&&millis()-lastClockAt>5000){drawClock();lastClockAt=millis();}
 delay(2);
}
