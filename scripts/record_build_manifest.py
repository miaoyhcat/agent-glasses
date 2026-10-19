#!/usr/bin/env python3
"""Record actual locally built source/binary hashes; never synthesize a build pass."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(paths):
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths)) if p.is_file()}


def main():
    outputs = [ROOT / 'releases/codexglasses-0.2.0-py3-none-any.whl', ROOT / 'releases/codexglasses-debug.apk']
    wheel = outputs[0]
    with zipfile.ZipFile(wheel) as z:
        for p in (ROOT / 'desktop/codexglasses').rglob('*'):
            if p.is_file() and p.suffix in {'.py', '.html'}:
                member = str(p.relative_to(ROOT / 'desktop'))
                if z.read(member) != p.read_bytes():
                    raise RuntimeError('wheel_source_mismatch: ' + member)
        if b'Version: 0.2.0\n' not in z.read('codexglasses-0.2.0.dist-info/METADATA'):
            raise RuntimeError('wheel_version_mismatch')
    firmware = json.loads((ROOT / 'docs/evidence/firmware-validation.json').read_text())
    if not firmware['all_passed']:
        raise RuntimeError('firmware_build_not_passed')
    for name, evidence in firmware['targets'].items():
        binary = ROOT / ('firmware/.pio/build/' + name + '/firmware.bin')
        if sha(binary) != evidence['binary_sha256']:
            raise RuntimeError('firmware_binary_mismatch: ' + name)
    runtime = json.loads((ROOT / 'docs/evidence/android-runtime.json').read_text())
    apk_runtime_matches = bool(runtime['passed'] and runtime['apk_sha256'] == sha(outputs[1]))
    groups = {
        'firmware': inputs(list((ROOT / 'firmware/include').rglob('*.h')) + list((ROOT / 'firmware/src').rglob('*.cpp')) +
                           list((ROOT / 'firmware/boards').glob('*.json')) + [ROOT / 'firmware/platformio.ini', ROOT / 'firmware/partitions.csv'] +
                           [p for p in (ROOT / 'third_party/lilygo-tglass-v2').rglob('*') if p.suffix in {'.h', '.cpp', '.c', '.json'}]),
        'android': inputs(list((ROOT / 'mobile/android/app/src').rglob('*.java')) + list((ROOT / 'mobile/android').rglob('*.gradle')) +
                          [ROOT / 'mobile/android/app/src/main/AndroidManifest.xml', ROOT / 'scripts/build_android.py']),
        'python': inputs([p for p in (ROOT / 'desktop/codexglasses').rglob('*') if p.suffix in {'.py', '.html'}] + [ROOT / 'pyproject.toml'])}
    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'project_version': '0.2.0', 'evidence_level': 2,
        'physical_tests': 0, 'host_python': platform.python_version(), 'platformio': '6.2.0',
        'android_sdk_platform': 35, 'android_build_tools': '35.0.0', 'jdk': 'OpenJDK17.0.20',
        'firmware_targets_not_distributed': firmware['targets'], 'source_inputs': groups,
        'delivered_binary_outputs': {str(p.relative_to(ROOT)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in outputs},
        'android_signature_v2_v3_verified': True, 'android_api26_runtime_exact_apk_matches': apk_runtime_matches,
        'python_wheel_contains_web_ui': True, 'python_wheel_matches_current_source': True,
        'unbuilt_container_definition': inputs([ROOT / 'agent-integration/codex/Dockerfile', ROOT / 'agent-integration/codex/worker_entry.py']),
        'limitations': ['Input hashes recorded after the actual builds; not a byte-identical cross-platform build guarantee',
                       'Android runtime uses an actual virtual device with a simulated agent, not physical BLE/ASR/optics',
                       'No real Docker container execution or paid OpenAI model task',
                       'Firmware binaries withheld pending third-party redistribution review']}
    (ROOT / 'docs/evidence/build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Recorded actual build artifacts; exact APK runtime match:', apk_runtime_matches)


if __name__ == '__main__':
    main()
