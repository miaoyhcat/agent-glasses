# Operating the current prototype

[中文](user-guide.md) · **English**

Today's entry points are the desktop workbench and the Android debug app; there is no
complete physical pair of glasses you can buy. Run the simulator from the README first, and
only then consider wiring up a D0 bench board.

Register on the computer only the project directories you are willing to hand to an agent.
The phone verifies the certificate and then pairs; never treat the operator token as a phone
token. Pick the device that matches the computer address, then the project and the action,
speak, check the transcript, then send. The computer sees the full instruction and approves;
the HUD shows waiting, preparing, running, cancelling, or the result. `unknown` means "go back
to the computer and look" — never read it as done.

After inspect completes, tick "continue the last completed task" and send "fix the problems
found". Once the authorized copy is writable, the fix lives only in that same copy; send test
next to run the existing tests. Merging back into the original project is a manual step done
on the computer. There is no entry point that publishes code automatically, sends content to
other people, or lets the glasses touch an arbitrary host path.

D0 requires the physical permission switch before a photo; the capture status LED should be
clearly visible in the real world. A short press of BOOT takes an offline photo, and media
that has not been transferred stays on the glasses — do not clear the cache before receipt is
confirmed. After the phone chooses to sync media it verifies and stores it; uploading to the
computer is a separate step that can resume after failure. Formatting the cache deletes media,
so only do it when you are sure it can be cleared.

AI voice/image analysis must be enabled explicitly on the computer, and the phone asks again
for consent to upload and for possible cost. Transcribed text is not forwarded to Codex
automatically. Phone TTS speaks directly; the glasses' short-audio path is an experimental
cache-and-play, waits for the transfer, and lasts at most 8 seconds — it is not a verified
natural real-time conversation experience.

Notification relay starts empty, and after the system permission is granted you still have to
choose apps. Showing only a title can still leak private information; you decide which apps
are appropriate. Today the phone stops polling tasks when it goes to the background; the
prototype does not promise an all-day background connection.

Do not treat the D0 bench as a finished product for outdoors, driving, sports or long wear.
H1 thermal, optical, battery and wear validation is not complete; those experiments follow the
acceptance matrix.
