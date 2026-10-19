# Android companion / v0.2

[中文](README.md) · **English**

Native Java for Android API 26+, compiled against API 35. Built directly with the official SDK,
v2/v3 signature checked; the API 26 emulator has run TLS pairing, task submission, desktop
approval and status display. The agent used in emulator tests is explicitly a SIMULATOR, not a
Codex model execution. The API 35 system image did not reach boot acceptance this time.

~~~bash
python scripts/build_android.py --sdk <official Android SDK directory>
adb install -r build/android/codexglasses-debug.apk
~~~

The Android Studio/Gradle sources are kept, but this round executed a direct SDK build. The
debug signature is not a production release signature; this round reuses the previously
delivered debug signature so upgrades keep their identity. If your own build does not match the
signature, do not uninstall the app before backing up media. The automated test's `--fresh-app`
only removes the test app inside this project's temporary AVD and is not meant for personal
device data.

## Usage and reliability

1. Verify the computer's full certificate fingerprint and real address, then pair. Only HTTPS
   is accepted, hostname verification is kept, and redirects are not followed. Tokens are
   isolated per certificate, protected by an Android Keystore AES-GCM key, and excluded from
   system backup.
2. Choose the project, action, and Chinese/English speech or text; check it, then send. The
   confirmation is bound to the current connection target, so switching computers requires
   confirming again. A retry ID is kept only for submissions that received no reply and is
   cleared once a reply arrives.
3. Starts only after local approval on the computer. The phone shows real status/steps/results
   and never computes a fictional percentage. `completed` is the end of the agent's turn, not a
   proof that the tests are correct.
4. D0 needs a system-level encrypted bond and a USB-provisioned key. P1 T-Glass V2 uses its own
   address/key, and display connectivity can coexist with D0; it is not compatible with Halo's
   proprietary protocol.
5. The glasses may delete local cache only after media chunking, fsync, SHA-256 and atomic
   metadata are complete. Restore supports both legacy numeric IDs and the new 128-bit base32
   IDs. A repeated announcement can verify an already stored file; an ID/content conflict is
   refused rather than overwritten.
6. Uploads persist the idempotent ID first and resume from the offset on retry; a single corrupt
   record is kept and skipped without blocking other media. Recent media is chosen by received
   time, not by upload mtime.
7. ASR and vision require explicit consent to upload and cost, and are off by default on the
   computer; a transcript never starts a task automatically. System speech recognition may go
   online by itself, so offline behaviour and noise figures are not promised.
8. Phone TTS or bounded short audio is sent to the glasses; a unique utterance callback prevents
   reusing an old file. BLE buffered playback latency and audio quality are not accepted.
9. Notifications are off by default and forward only the title of apps the user selected; a
   title can still be private, and the body is never uploaded.

Polling allows a single in-flight request and never queues them; control, cancel, receive and
upload are each bounded. BLE writes one acknowledged packet at a time, the HUD merges to the
latest value, and the real MTU is negotiated. A full queue is refused explicitly, and
unacknowledged media stays on the glasses. None of this is claimed to have passed weak-signal
testing.

## Reproducible run checks

~~~bash
python scripts/check_java_audio.py
python scripts/check_java_reliability.py
python scripts/check_android_runtime.py --sdk <official Android SDK directory> --api 26 --boot-timeout 420
~~~

These need the official emulator, platform-tools and an AOSP API 26 x86_64 system image. The
scripts only target a separate test AVD and disable metrics collection. Without KVM the
environment falls back to software CPU emulation and may be very slow. A real run record
includes the SHA-256 of the installed APK; a failed record is never edited into a pass.

This is still a foreground Activity prototype: polling stops when it goes to the background, and
there is no compliant all-day background CompanionDeviceService. Real-device BLE, noisy-room
ASR, audio loopback, low latency, media power-loss and OTA are not accepted. There is no native
iOS app, and a web entry point cannot replace iOS media/notification support for the glasses.
