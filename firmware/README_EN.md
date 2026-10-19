# D0 / P1 firmware: cross-compiled, not flashed on hardware

[中文](README.md) · **English**

The hardware is an ESP32-S3-WROOM-1-N16R8 development board plus peripherals; the exact wiring
is in `include/pins.h` and `hardware/assembly/d0-wiring.csv`. D0 has no VGA020/transparent
optical engine driver. A separate P1 TGlass V2 near-eye display firmware is also provided; it is
a split development platform alongside D0, not the H1 lightweight integrated unit.

## Drivers actually written

- ST7789 SPI 240×240 initialization, a 1-bit 128×64 phone-rasterized HUD, and a simple standalone
  clock. The phone syncs Unix time and timezone through an authenticated `status` message; before
  time is set on a cold boot the display shows `--:--` rather than an invented time.
- OV2640 DVP JPEG capture; the physical permission input must be high; the file is written
  locally before any media is announced. A short BOOT press takes a standalone photo. GPIO0's
  boot role must still be respected during reset/flash.
- Short JPEG frame recording at a 320×240 target of 5 fps, up to 15 seconds, with real
  timestamps; the actual frame rate is still to be measured. It can cache without the phone, but
  there is no complete local menu.
- I2S microphone 16 kHz PCM16 WAV, up to 8 seconds; MAX98357A prompt tones and short PCM speech
  playback. Phone TTS files are converted to 16 kHz mono, chunk-cached in PSRAM, SHA-256
  verified, then played. BLE transfer waits are currently long: **the verified low-latency voice
  goal is not met**.
- SD first, internal SPIFFS fallback; failing media is never auto-formatted; insufficient
  capacity refuses capture and never overwrites unacknowledged media. The SPIFFS partition is
  about 9.94 MiB and must not be advertised as large long-term recording.
- BLE encrypted bonding, USB physical key provisioning, a random session per boot, HMAC
  authentication, monotonic sequence numbers, replay protection, and command length/queue
  limits.

## Build, configure, flash

```bash
python -m pip install platformio
python scripts/build_firmware.py
# Choose the bench target explicitly and confirm wiring before flashing; the steps below need real hardware
PLATFORMIO_SETTING_ENABLE_TELEMETRY=no python -m platformio run -d firmware -e codexglasses_d0 -t upload
python -m platformio device monitor -b 115200
```

Confirm the module really has 16 MB flash and 8 MB octal PSRAM. The custom board configuration
avoids applying an 8 MB board's default to a 16 MB cache partition. Do not move to GPIO35–37 —
they belong to this PSRAM variant. For first use of the internal cache, hold BOOT in the USB
terminal, then send `format-cache` and press enter; this erases internal media and should only be
used on first media you are sure can be cleared. An SD card should be formatted and checked on a
computer first.

Generate a 32-byte random accessory key and store it safely; hold BOOT over USB, send
`provision ` followed by the 64-character hex key, then press enter. The firmware never echoes
the key. The Bluetooth pairing passkey is printed to the USB terminal; after the Android system
completes encrypted bonding, the phone configures the same HMAC key. Serial tools may keep the
provisioning input in their history, so use a trusted tool.

## Not implemented or verified

No signed OTA, secure boot, flash encryption, Wi-Fi burst media protocol, dual-mic beamforming,
AEC, offline natural-language ASR, standalone wake word, contact-surface temperature loop or H1
low-power state scheduling. The main loop's 2 ms polling and the bench backlight do not meet the
H1 power budget. Battery level stays null; an uncalibrated ADC value is never mapped to a
percentage.

Cache flush/rename and phone fsync reduce loss risk, but SPIFFS/SD still need fault-injection
trials for power loss, wear, FAT directory updates and card removal. Short audio uses a bounded
cache and simple resampling — this is not audio-quality or latency acceptance. Cross-platform BLE
connection, PASSKEY interaction, real display offset, I2S slots, speaker volume and camera
timing all await hardware verification.

D0 may only be powered and tested on an off-body development fixture. The camera power test
board does not isolate reverse power feed through DVP/SCCB/XCLK; full physical privacy and
thermal safety are not accepted.

## P1: a near-eye display with a real purchasing path

`codexglasses_tglass_v2` is a separate ESP32-S3 / TGlass V2 display target;
`scripts/build_firmware.py` builds both D0 and P1 and saves both real exit codes, memory usage
and image hashes. P1 uses a fixed version of the vendor's MIT-licensed driver; source and license
are in `third_party/lilygo-tglass-v2/`.

```bash
PLATFORMIO_SETTING_ENABLE_TELEMETRY=no python -m platformio run -d firmware -e codexglasses_tglass_v2 -t upload
```

P1 keeps the left and right edges of the phone's 128×64 bitmap and maps it into a 126×126 display
window; it supports the standalone clock, USB key provisioning, encrypted BLE bonding and the HMAC
HUD. `photo/record/audio/read` explicitly return unsupported on this configuration; capture is
handled by D0 or the phone. Android can bind the capture board and the display board separately,
each with its own key. Full purchasing, display window and USB BOOT provisioning steps are in the
[P1 guide](../hardware/optics/p1-tglass-v2.md).

In v0.2 a media ID is a 26-character lowercase Base32 string of a 128-bit random value;
`/` + ID + `.jpg` + NUL is 32 bytes, fitting the current SPIFFS filename limit, and temporary
files use `.p`. Legacy 1–10 digit numeric IDs remain readable. The firmware headers have passed
256 cross-language vectors and raster boundary tests; this does not prove storage power-loss
safety or DMA display timing.

**Both P1 and D0 have only been compiled and covered by host-side core tests. There are no
records of flashing, real near-eye display, BLE, camera or audio on hardware.**
