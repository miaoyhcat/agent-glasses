// CodexGlasses D0: implemented drivers for a bench rig. H1 optics remain gated.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <FS.h>
#include <SPIFFS.h>
#include <SD.h>
#include <Preferences.h>
#include <NimBLEDevice.h>
#include <esp_camera.h>
#include <esp_sleep.h>
#include <driver/i2s.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <mbedtls/base64.h>
#include <sys/time.h>
#include "pins.h"
#include "media_id.h"
#ifdef CONFIG_SPIFFS_OBJ_NAME_LEN
static_assert(CONFIG_SPIFFS_OBJ_NAME_LEN>=32,"SPIFFS filenames must support 32 bytes including NUL");
#endif

static Preferences prefs;
static uint8_t keyBytes[32];
static bool provisioned=false,sdReady=false,cameraReady=false;
static volatile bool bleAuthenticated=false;
static volatile uint16_t bleHandle=0xffff;
static uint64_t lastSeq=0;
static String sessionId,serialLine,bleLine;
static NimBLECharacteristic* tx=nullptr;
static QueueHandle_t commands;
static SemaphoreHandle_t sendMutex;
static fs::FS* cache=&SPIFFS;
RTC_DATA_ATTR bool clockValid=false;
RTC_DATA_ATTR int timezoneMinutes=0;
static uint32_t lastHudAt=0,lastClockAt=0,lastProvisionAt=0,buttonDownAt=0;
static bool buttonDown=false;
static uint8_t* speakerBuffer=nullptr;static size_t speakerSize=0,speakerReceived=0;static String speakerHash;static uint32_t speakerTouched=0;
static const size_t CACHE_RESERVE=512*1024;
static const char* SERVICE="6e400001-b5a3-f393-e0a9-e50e24dcca9e";
static const char* RX_UUID="6e400002-b5a3-f393-e0a9-e50e24dcca9e";
static const char* TX_UUID="6e400003-b5a3-f393-e0a9-e50e24dcca9e";

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
  j["profile"]="D0_ST7789_240";j["provisioned"]=provisioned;j["media_link_encrypted"]=true;emit(j);
  if(tx){String readable;serializeJson(j,readable);readable+='\n';tx->setValue(readable.c_str());}}

// ST7789 240x240 SPI bench display; never presented as a bonded near-eye module.
void lcdCommand(uint8_t cmd,const uint8_t* data=nullptr,size_t n=0){
  SPI.beginTransaction(SPISettings(20000000,MSBFIRST,SPI_MODE0));
  digitalWrite(DISPLAY_CS,LOW);digitalWrite(DISPLAY_DC,LOW);SPI.transfer(cmd);
  digitalWrite(DISPLAY_DC,HIGH);for(size_t i=0;i<n;i++)SPI.transfer(data[i]);
  digitalWrite(DISPLAY_CS,HIGH);SPI.endTransaction();
}
void lcdWindow(uint16_t x,uint16_t y,uint16_t w,uint16_t h){
  uint8_t a[4]={(uint8_t)(x>>8),(uint8_t)x,(uint8_t)((x+w-1)>>8),(uint8_t)(x+w-1)};
  uint8_t b[4]={(uint8_t)(y>>8),(uint8_t)y,(uint8_t)((y+h-1)>>8),(uint8_t)(y+h-1)};
  lcdCommand(0x2a,a,4);lcdCommand(0x2b,b,4);lcdCommand(0x2c);
}
void lcdFill(uint16_t color){lcdWindow(0,0,240,240);
  SPI.beginTransaction(SPISettings(20000000,MSBFIRST,SPI_MODE0));digitalWrite(DISPLAY_CS,LOW);digitalWrite(DISPLAY_DC,HIGH);
  for(int i=0;i<240*240;i++)SPI.transfer16(color);digitalWrite(DISPLAY_CS,HIGH);SPI.endTransaction();}
void lcdInit(){
  for(int pin:{DISPLAY_CS,DISPLAY_DC,DISPLAY_RST,SD_CS})pinMode(pin,OUTPUT);
  digitalWrite(DISPLAY_CS,HIGH);digitalWrite(SD_CS,HIGH);digitalWrite(DISPLAY_RST,LOW);delay(15);
  digitalWrite(DISPLAY_RST,HIGH);delay(120);lcdCommand(0x01);delay(150);lcdCommand(0x11);delay(120);
  uint8_t mode=0x55,madctl=0; lcdCommand(0x3a,&mode,1);lcdCommand(0x36,&madctl,1);lcdCommand(0x21);lcdCommand(0x29);lcdFill(0);
}
bool drawBitmap(const String& encoded){
  uint8_t pixels[1024];size_t n=0;
  if(mbedtls_base64_decode(pixels,sizeof(pixels),&n,(const uint8_t*)encoded.c_str(),encoded.length())||n!=1024)return false;
  lcdWindow(56,88,128,64);SPI.beginTransaction(SPISettings(20000000,MSBFIRST,SPI_MODE0));
  digitalWrite(DISPLAY_CS,LOW);digitalWrite(DISPLAY_DC,HIGH);
  for(size_t i=0;i<1024;i++)for(int bit=7;bit>=0;bit--)SPI.transfer16(pixels[i]&(1<<bit)?0x87f0:0);
  digitalWrite(DISPLAY_CS,HIGH);SPI.endTransaction();return true;
}
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

bool spaceAvailable(size_t requested){
  uint64_t total=sdReady?SD.totalBytes():SPIFFS.totalBytes();
  uint64_t used=sdReady?SD.usedBytes():SPIFFS.usedBytes();
  return total>=used&&total-used>requested+CACHE_RESERVE;
}
bool fileHash(const String& path,String& out){
  File f=cache->open(path,"r");if(!f)return false;
  mbedtls_sha256_context ctx;mbedtls_sha256_init(&ctx);mbedtls_sha256_starts_ret(&ctx,0);
  uint8_t buffer[512],hash[32];while(f.available()){size_t n=f.read(buffer,sizeof(buffer));mbedtls_sha256_update_ret(&ctx,buffer,n);}
  mbedtls_sha256_finish_ret(&ctx,hash);mbedtls_sha256_free(&ctx);out=hexBytes(hash,32);return true;
}
String mediaPath(const String& id){
  bool legacy=id.length()>=1&&id.length()<=10,modern=id.length()==26;
  if(!legacy&&!modern)return "";for(char c:id)if(!(legacy?(c>='0'&&c<='9'):((c>='a'&&c<='z')||(c>='2'&&c<='7'))))return "";
  for(const char* ext:{".jpg",".v",".agmj",".wav"}){String p="/"+id+ext;if(cache->exists(p))return p;}return "";
}
void announce(const String& path){
  String sha;if(!fileHash(path,sha)){error("media_hash_failed");return;}
  File f=cache->open(path,"r");StaticJsonDocument<320> j;j["v"]=1;j["type"]="media";
  j["id"]=path.substring(1,path.lastIndexOf('.'));j["size"]=f.size();j["sha256"]=sha;
  j["mime"]=path.endsWith(".jpg")?"image/jpeg":path.endsWith(".wav")?"audio/wav":"video/x-motion-jpeg";emit(j);
}
bool cameraOn(framesize_t frameSize){
  if(digitalRead(PRIVACY_READY)!=HIGH){error("physical_privacy_interlock_open");return false;}
  digitalWrite(CAMERA_GATE,HIGH);delay(100);
  camera_config_t c={};c.pin_pwdn=-1;c.pin_reset=-1;c.pin_xclk=CAM_XCLK;c.pin_sccb_sda=CAM_SDA;c.pin_sccb_scl=CAM_SCL;
  c.pin_d0=CAM_D0;c.pin_d1=CAM_D1;c.pin_d2=CAM_D2;c.pin_d3=CAM_D3;c.pin_d4=CAM_D4;c.pin_d5=CAM_D5;c.pin_d6=CAM_D6;c.pin_d7=CAM_D7;
  c.pin_vsync=CAM_VSYNC;c.pin_href=CAM_HREF;c.pin_pclk=CAM_PCLK;c.xclk_freq_hz=20000000;
  c.ledc_timer=LEDC_TIMER_0;c.ledc_channel=LEDC_CHANNEL_0;c.pixel_format=PIXFORMAT_JPEG;
  // Allocate the framebuffer for the requested capture size at initialization.
  c.frame_size=frameSize;c.jpeg_quality=14;c.fb_count=1;c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;c.fb_location=CAMERA_FB_IN_PSRAM;
  if(esp_camera_init(&c)!=ESP_OK){digitalWrite(CAMERA_GATE,LOW);error("camera_init_failed");return false;}
  cameraReady=true;return true;
}
void cameraOff(){if(cameraReady){esp_camera_deinit();cameraReady=false;}digitalWrite(CAMERA_GATE,LOW);}
String newPath(const char* ext){for(int i=0;i<16;i++){uint8_t id[16];char stem[27];esp_fill_random(id,sizeof(id));encodeMediaId(id,stem);String p="/"+String(stem)+ext;if(!cache->exists(p))return p;}return "";}
void capture(bool video,unsigned seconds){
  if(!spaceAvailable(video?seconds*180000:400000)){error("cache_full_export_required");return;}
  if(!cameraOn(video?FRAMESIZE_QVGA:FRAMESIZE_SVGA))return;String finalPath=newPath(video?".v":".jpg"),temp=finalPath.substring(0,finalPath.lastIndexOf('.'))+".p";
  if(finalPath.isEmpty()){cameraOff();error("id_allocation_failed");return;}
  File out=cache->open(temp,"w");bool okay=(bool)out;
  if(video&&okay)okay=out.write((const uint8_t*)"AGMJ1",5)==5;
  unsigned frames=video?seconds*5:1;
  if(!video)delay(100);
  uint32_t start=millis();
  for(unsigned i=0;i<frames&&okay;i++){
    if(digitalRead(PRIVACY_READY)!=HIGH){okay=false;break;}
    camera_fb_t* fb=esp_camera_fb_get();if(!fb){okay=false;break;}
    if(!spaceAvailable(fb->len+16)){esp_camera_fb_return(fb);okay=false;break;}
    if(video){uint32_t stamp=millis()-start,length=fb->len;okay=out.write((uint8_t*)&stamp,4)==4&&out.write((uint8_t*)&length,4)==4;}
    if(okay)okay=out.write(fb->buf,fb->len)==fb->len;
    esp_camera_fb_return(fb);out.flush();
    if(video){int32_t remaining=(int32_t)((i+1)*200)-(int32_t)(millis()-start);if(remaining>0)delay(remaining);}
  }
  out.close();cameraOff();
  if(!okay||!cache->rename(temp,finalPath)){cache->remove(temp);error("capture_failed_no_ack");return;}
  announce(finalPath);
}
bool i2sInit(){
  i2s_config_t config={};config.mode=(i2s_mode_t)(I2S_MODE_MASTER|I2S_MODE_RX|I2S_MODE_TX);
  config.sample_rate=16000;config.bits_per_sample=I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format=I2S_CHANNEL_FMT_ONLY_LEFT;config.communication_format=I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags=0;config.dma_buf_count=4;config.dma_buf_len=256;config.use_apll=false;
  config.tx_desc_auto_clear=true;
  i2s_pin_config_t pins={};pins.bck_io_num=AUDIO_BCLK;pins.ws_io_num=AUDIO_WS;pins.data_out_num=AUDIO_DATA;pins.data_in_num=MIC_DATA;pins.mck_io_num=I2S_PIN_NO_CHANGE;
  return i2s_driver_install(I2S_NUM_0,&config,0,nullptr)==ESP_OK&&i2s_set_pin(I2S_NUM_0,&pins)==ESP_OK;
}
void recordAudio(unsigned seconds){
  if(!spaceAvailable(seconds*32000+44)){error("cache_full_export_required");return;}
  if(!i2sInit()){error("audio_init_failed");return;}
  String path=newPath(".wav"),temp=path.substring(0,path.lastIndexOf('.'))+".p";File f=cache->open(temp,"w");bool okay=(bool)f;
  uint32_t dataSize=seconds*32000,riffSize=dataSize+36,rate=16000,byteRate=32000;
  uint16_t pcm=1,mono=1,align=2,bits=16;uint32_t fmtSize=16;
  f.write((const uint8_t*)"RIFF",4);f.write((uint8_t*)&riffSize,4);f.write((const uint8_t*)"WAVEfmt ",8);
  f.write((uint8_t*)&fmtSize,4);f.write((uint8_t*)&pcm,2);f.write((uint8_t*)&mono,2);f.write((uint8_t*)&rate,4);
  f.write((uint8_t*)&byteRate,4);f.write((uint8_t*)&align,2);f.write((uint8_t*)&bits,2);f.write((const uint8_t*)"data",4);f.write((uint8_t*)&dataSize,4);
  int32_t input[256];int16_t output[256];uint32_t written=0;
  while(okay&&written<dataSize){size_t got=0;
    if(i2s_read(I2S_NUM_0,input,sizeof(input),&got,pdMS_TO_TICKS(1000))!=ESP_OK||!got){okay=false;break;}
    size_t n=min(got/4,(size_t)(dataSize-written)/2);for(size_t i=0;i<n;i++)output[i]=(int16_t)(input[i]>>16);
    okay=f.write((uint8_t*)output,n*2)==n*2;written+=n*2;
  }f.flush();f.close();i2s_driver_uninstall(I2S_NUM_0);
  if(!okay||!cache->rename(temp,path)){cache->remove(temp);error("audio_record_failed");return;}announce(path);
}
void playTone(){
  if(!i2sInit()){error("audio_init_failed");return;}
  digitalWrite(AUDIO_ENABLE,HIGH);int32_t buffer[160];
  for(int block=0;block<20;block++){for(int i=0;i<160;i++)buffer[i]=((i%16)<8?1:-1)*(1<<22);
    size_t sent=0;i2s_write(I2S_NUM_0,buffer,sizeof(buffer),&sent,pdMS_TO_TICKS(100));}
  digitalWrite(AUDIO_ENABLE,LOW);i2s_driver_uninstall(I2S_NUM_0);
}
void speakerReset(){if(speakerBuffer)free(speakerBuffer);speakerBuffer=nullptr;speakerSize=speakerReceived=0;speakerHash="";}
void speakerAck(){StaticJsonDocument<128> j;j["v"]=1;j["type"]="speaker_ack";j["offset"]=speakerReceived;emit(j);}
void speakerPlay(){
  uint8_t hash[32];mbedtls_sha256_ret(speakerBuffer,speakerSize,hash,0);
  if(speakerReceived!=speakerSize||hexBytes(hash,32)!=speakerHash){speakerReset();error("speaker_integrity_failed");return;}
  if(!i2sInit()){speakerReset();error("speaker_init_failed");return;}
  digitalWrite(AUDIO_ENABLE,HIGH);bool okay=true;int32_t out[256];
  for(size_t offset=0;offset<speakerSize&&okay;){size_t samples=min((speakerSize-offset)/2,(size_t)256);
    for(size_t i=0;i<samples;i++){int16_t value=(int16_t)(speakerBuffer[offset+2*i]|(speakerBuffer[offset+2*i+1]<<8));out[i]=(int32_t)value*65536;}
    size_t wrote=0;okay=i2s_write(I2S_NUM_0,out,samples*4,&wrote,pdMS_TO_TICKS(1000))==ESP_OK&&wrote==samples*4;offset+=samples*2;
  }
  // Allow the final DMA block to drain before muting; hardware timing still needs QA.
  delay(80);digitalWrite(AUDIO_ENABLE,LOW);i2s_driver_uninstall(I2S_NUM_0);speakerReset();if(!okay)error("speaker_write_failed");
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
  if(speakerBuffer&&op!="speaker_data"&&op!="speaker_play"&&op!="hud"&&op!="status"){error("speaker_upload_busy");return;}
  if(op=="speaker_start"){
    int size=body["bytes"]|0;String sha=body["sha256"]|String("");uint8_t expected[32];
    if(size<2||size>256000||size%2||!decodeHex(sha,expected,32)){error("speaker_pcm16_16khz_max8s_required");return;}
    speakerBuffer=(uint8_t*)ps_malloc(size);if(!speakerBuffer){error("speaker_no_memory");return;}
    speakerSize=size;speakerReceived=0;speakerHash=sha;speakerTouched=millis();speakerAck();return;
  }else if(op=="speaker_data"){
    String data=body["data"]|String("");int offset=body["offset"]|-1;uint8_t bytes[384];size_t n=0;
    if(!speakerBuffer||offset!=(int)speakerReceived||data.length()>512||mbedtls_base64_decode(bytes,sizeof(bytes),&n,(uint8_t*)data.c_str(),data.length())||n==0||speakerReceived+n>speakerSize){error("speaker_chunk_invalid");return;}
    memcpy(speakerBuffer+speakerReceived,bytes,n);speakerReceived+=n;speakerTouched=millis();speakerAck();return;
  }else if(op=="speaker_play"){
    if(!speakerBuffer){error("speaker_no_data");return;}speakerPlay();
  }else if(op=="hud"){
    if(!body["bitmap"].is<const char*>()||!drawBitmap(body["bitmap"].as<String>())){error("bitmap_128x64_required");return;}
    lastHudAt=millis();
  }else if(op=="photo"){capture(false,0);return;}
  else if(op=="record"){int seconds=body["seconds"]|0;if(seconds<1||seconds>15){error("invalid_duration");return;}capture(true,seconds);return;}
  else if(op=="audio"){
    if(body["tone"]==true)playTone();else{int seconds=body["seconds"]|0;if(seconds<1||seconds>8){error("invalid_duration");return;}recordAudio(seconds);return;}
  }else if(op=="list"){
    File root=cache->open("/");File f=root.openNextFile();while(f){String p=f.path();if(!f.isDirectory()&&!p.endsWith(".part")&&!p.endsWith(".p"))announce(p);f=root.openNextFile();}
  }else if(op=="read"){
    String path=mediaPath(body["id"]|String(""));int offset=body["offset"]|-1;
    if(path.isEmpty()||offset<0){error("invalid_media_request");return;}
    File f=cache->open(path,"r");if((size_t)offset>=f.size()||!f.seek(offset)){error("invalid_offset");return;}
    uint8_t bytes[384],encoded[520];size_t n=f.read(bytes,sizeof(bytes)),out=0;
    mbedtls_base64_encode(encoded,sizeof(encoded),&out,bytes,n);
    StaticJsonDocument<1024> j;j["v"]=1;j["type"]="chunk";j["id"]=body["id"];j["offset"]=offset;j["data"]=String((char*)encoded,out);emit(j);return;
  }else if(op=="ack"){
    String path=mediaPath(body["id"]|String("")),sha;
    if(path.isEmpty()||!fileHash(path,sha)||sha!=(body["sha256"]|String(""))){error("ack_hash_mismatch");return;}
    if(!cache->remove(path)){error("cache_delete_failed");return;}
  }else if(op=="sleep"){
    cameraOff();digitalWrite(AUDIO_ENABLE,LOW);lcdCommand(0x28);
    esp_sleep_enable_ext0_wakeup((gpio_num_t)USER_BUTTON,0);delay(100);esp_deep_sleep_start();
  }else if(op!="status"){error("unsupported_operation");return;}
  if(op=="status"&&body["unix"].is<uint64_t>()){
    uint64_t epoch=body["unix"].as<uint64_t>();int zone=body["tz_minutes"]|0;
    if(epoch<1577836800ULL||epoch>2145916800ULL||zone<-840||zone>840){error("invalid_time");return;}
    struct timeval value={(time_t)epoch,0};settimeofday(&value,nullptr);timezoneMinutes=zone;clockValid=true;
  }
  StaticJsonDocument<320> j;j["v"]=1;j["type"]="status";j["profile"]="D0";j["last_seq"]=lastSeq;
  j["battery_percent"]=nullptr;j["storage"]=sdReady?"SD":"SPIFFS";j["privacy_ready"]=digitalRead(PRIVACY_READY)==HIGH;emit(j);
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
  if(esp_reset_reason()!=ESP_RST_DEEPSLEEP)clockValid=false;
  pinMode(CAMERA_GATE,OUTPUT);digitalWrite(CAMERA_GATE,LOW);pinMode(PRIVACY_READY,INPUT_PULLDOWN);
  pinMode(AUDIO_ENABLE,OUTPUT);digitalWrite(AUDIO_ENABLE,LOW);pinMode(USER_BUTTON,INPUT_PULLUP);
  uint8_t randomSession[16];esp_fill_random(randomSession,16);sessionId=hexBytes(randomSession,16);
  prefs.begin("codexglasses",false);provisioned=prefs.getBytesLength("key")==32;if(provisioned)prefs.getBytes("key",keyBytes,32);
  SPI.begin(SPI_SCK,SPI_MISO,SPI_MOSI);lcdInit();drawClock();sdReady=SD.begin(SD_CS,SPI,10000000);
  if(sdReady)cache=&SD;else if(!SPIFFS.begin(false)){error("cache_not_formatted_uploadfs_required");}
  // Pairing passkey is shown on USB console; D0 has no font renderer.
  uint32_t passkey=100000+(esp_random()%900000);Serial.printf("BLE pairing passkey: %06lu\n",(unsigned long)passkey);
  NimBLEDevice::init("CodexGlasses-D0");NimBLEDevice::setMTU(247);NimBLEDevice::setSecurityAuth(true,true,true);
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
      if(serialLine=="format-cache"&&digitalRead(USER_BUTTON)==LOW&&!sdReady){
        SPIFFS.end();bool okay=SPIFFS.format()&&SPIFFS.begin(false);serialLine="";
        if(okay)hello();else error("cache_format_failed");
      }else if(serialLine.startsWith("provision ")&&digitalRead(USER_BUTTON)==LOW){
        uint8_t newKey[32];if(decodeHex(serialLine.substring(10),newKey,32)){
          prefs.putBytes("key",newKey,32);memcpy(keyBytes,newKey,32);provisioned=true;lastSeq=0;lastProvisionAt=millis();
          esp_fill_random(newKey,16);sessionId=hexBytes(newKey,16);hello();
        }else error("invalid_key");serialLine="";
      }else enqueue(serialLine);
    }else if(c!='\r'){serialLine+=c;if(serialLine.length()>=4096){serialLine="";error("frame_too_large");}}
  }
  char* command=nullptr;if(xQueueReceive(commands,&command,0)==pdTRUE){execute(String(command));free(command);}
  if(speakerBuffer&&millis()-speakerTouched>30000){speakerReset();error("speaker_upload_timeout");}
  bool pressed=digitalRead(USER_BUTTON)==LOW;
  if(pressed&&!buttonDown){buttonDown=true;buttonDownAt=millis();}
  if(!pressed&&buttonDown){buttonDown=false;uint32_t held=millis()-buttonDownAt;
    if(held>30&&held<1000&&millis()-lastProvisionAt>3000)capture(false,0);
  }
  if(millis()-lastHudAt>3500&&millis()-lastClockAt>5000){drawClock();lastClockAt=millis();}
  delay(2);
}
