#pragma once
// D0 wired development rig. NOT the final H1 optical-engine pinout.
// ESP32-S3-WROOM-1-N16R8: GPIO35..37 belong to octal PSRAM; do not use.
constexpr int CAM_XCLK=15, CAM_PCLK=13, CAM_VSYNC=6, CAM_HREF=7;
constexpr int CAM_SDA=4, CAM_SCL=5;
constexpr int CAM_D0=11,CAM_D1=9,CAM_D2=8,CAM_D3=10,CAM_D4=12,CAM_D5=18,CAM_D6=17,CAM_D7=16;
constexpr int CAMERA_GATE=2, PRIVACY_READY=42, USER_BUTTON=0;
constexpr int SPI_SCK=39,SPI_MOSI=40,SPI_MISO=43,DISPLAY_CS=41,DISPLAY_DC=38,DISPLAY_RST=44,SD_CS=3;
constexpr int AUDIO_BCLK=14,AUDIO_WS=21,MIC_DATA=47,AUDIO_DATA=48,AUDIO_ENABLE=45;
constexpr int BATTERY_ADC=1;
