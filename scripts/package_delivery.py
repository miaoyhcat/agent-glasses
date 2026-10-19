#!/usr/bin/env python3
"""Audit and create a source-complete, credential-free delivery ZIP.

Includes original source/designs/evidence and explicitly supplied debug APK and
Python wheel. Excludes toolchains, downloaded frameworks, runtime credentials,
temporary caches and the locally compiled third-party-linked firmware binary.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.pio','.venv','.gradle','__pycache__','build','runtime','dist','node_modules'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    result=[]
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if any(part in EXCLUDED or part.endswith('.egg-info') for part in rel.parts):continue
        if p.suffix in {'.pyc','.key','.pem','.jks','.db','.kicad_prl'} or '.db-' in p.name:continue
        if p.is_symlink():raise RuntimeError('Do not package symlinks: '+str(rel))
        if p.is_file() and p!=ROOT/'DELIVERY-MANIFEST.json':result.append(p)
    return result


def audit():
    required=['README.md','README_EN.md','LICENSE','NOTICE.md','SECURITY.md','docs/final-report.md',
      'docs/verification-report.md','docs/evidence-index.json','docs/acceptance-matrix.csv',
      'docs/evidence/build-manifest.json','docs/evidence/software-validation.json',
      'hardware/bom/components.csv','hardware/bom/mass-budget.csv','hardware/mechanical/generated/codexglasses-h1-fixture.step',
      'hardware/schematics/interlock.kicad_sch','hardware/pcb/interlock-test-coupon/interlock-test.kicad_pcb',
      'firmware/src/tglass_main.cpp','scripts/benchmark_codex_local.py','scripts/fixture_mcp.py','firmware/src/main.cpp','mobile/android/app/src/main/java/dev/codexglasses/MainActivity.java',
      'desktop/codexglasses/codex.py','simulator/demo.py','releases/codexglasses-debug.apk']
    for rel in required:
        if not (ROOT/rel).is_file():raise RuntimeError('Missing: '+rel)
    current=files();broken=[]
    for p in current:
        if p.suffix=='.json':json.loads(p.read_text())
        if p.suffix=='.md':
            for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if re.match(r'\w+://|mailto:|#|sandbox:',target):continue
                local=target.split('#')[0]
                if local and not (p.parent/local).exists():broken.append(str(p.relative_to(ROOT))+': '+target)
    if broken:raise RuntimeError('Broken local links: '+repr(broken))
    for rel in ['LICENSE','README.md','README_EN.md']:
        if '3277681859@qq.com' not in (ROOT/rel).read_text():raise RuntimeError('Missing commercial contact')
    sources=json.loads((ROOT/'docs/sources.json').read_text());ids={s['id'] for s in sources}
    if len(ids)!=len(sources):raise RuntimeError('Duplicate source IDs')
    markets=json.loads((ROOT/'docs/market-database.json').read_text())
    for m in markets:
        if not set(m['sources'].split('|'))<=ids:raise RuntimeError('Unresolved market citation')
    matrix=list(csv.DictReader((ROOT/'docs/acceptance-matrix.csv').open()))
    if any(r['evidence_level']=='1' for r in matrix):raise RuntimeError('No hardware was measured in this delivery')
    evidence=json.loads((ROOT/'docs/evidence/software-validation.json').read_text())
    if not evidence['all_passed'] or evidence['physical_hardware_tests']!=0:raise RuntimeError('Validation evidence inconsistent')
    manifest=json.loads((ROOT/'docs/evidence/build-manifest.json').read_text())
    for group,inputs in manifest['source_inputs'].items():
        for path,digest in inputs.items():
            if sha(ROOT/path)!=digest:raise RuntimeError('Built source changed: '+path)
    for path,meta in manifest['delivered_binary_outputs'].items():
        if sha(ROOT/path)!=meta['sha256']:raise RuntimeError('Binary changed: '+path)
    index=json.loads((ROOT/'docs/evidence-index.json').read_text())
    for claim in index['claims']:
        for key in ['implementation_or_input','record']:
            if not (ROOT/claim[key]).exists():raise RuntimeError('Unresolved evidence path: '+claim[key])
    if len({row['id'] for row in matrix})!=len(matrix):raise RuntimeError('Duplicate acceptance IDs')
    for row in matrix:
        if not (ROOT/row['evidence_or_plan']).exists():raise RuntimeError('Unresolved acceptance path: '+row['evidence_or_plan'])
    runtime=json.loads((ROOT/'docs/evidence/android-runtime.json').read_text())
    if not runtime['passed'] or runtime['apk_sha256']!=sha(ROOT/'releases/codexglasses-debug.apk'):
        raise RuntimeError('Delivered APK was not the tested Android artifact')
    firmware=json.loads((ROOT/'docs/evidence/firmware-validation.json').read_text())
    if not firmware['all_passed'] or set(firmware['targets'])!={'codexglasses_d0','codexglasses_tglass_v2'}:
        raise RuntimeError('Both firmware targets must have actual successful records')
    origin=ROOT/'third_party/lilygo-tglass-v2'
    vendor=json.loads((origin/'ORIGIN.json').read_text())
    for path,digest in vendor['files_sha256'].items():
        if sha(origin/path)!=digest:raise RuntimeError('Third-party source was modified: '+path)
    local=json.loads((ROOT/'docs/evidence/local-codex-broker.json').read_text())
    if local.get('passed'):
        if local.get('independent_test_exit')!=0 or not local.get('minimal_patch_security_guard') or not local.get('capability_limited_public_fixture_only'):
            raise RuntimeError('Public local-model acceptance lacks independent checks')
        if sha(ROOT/local['model_patch_artifact'])!=local['model_patch_sha256']:
            raise RuntimeError('Model patch artifact differs from acceptance')
    reproduction=json.loads((ROOT/'docs/evidence/local-codex-reproduction.json').read_text())
    for path,digest in reproduction.get('source_inputs',{}).items():
        if sha(ROOT/path)!=digest:raise RuntimeError('Tested model runner changed: '+path)
    wheel_runtime=json.loads((ROOT/'docs/evidence/wheel-runtime.json').read_text())
    if not wheel_runtime['passed'] or wheel_runtime['wheel_sha256']!=sha(ROOT/'releases/codexglasses-0.2.0-py3-none-any.whl'):
        raise RuntimeError('Delivered wheel differs from tested installation')
    private_pattern=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{32,}|\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}')
    for p in current:
        if private_pattern.search(p.read_bytes()):raise RuntimeError('Possible private credential: '+str(p.relative_to(ROOT)))
    return {'evidence_level':2,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'required_files_present':True,'local_markdown_links_valid':True,'build_input_output_hashes_match':True,
       'no_private_key_patterns_found':True,'source_count':len(sources),'market_product_count':len(markets),
       'acceptance_cases':len(matrix),'host_test_count':evidence['checks'][0]['test_count'],'physical_hardware_tests':0,
       'exact_android_runtime_artifact':True,'third_party_vendor_hashes_match':True,
       'local_model_public_fixture_passed':bool(local.get('passed')),
       'note':'Pattern scan is not a general secret or security audit. ZIP content is checked by SHA-256 on readback.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    target=a.output.resolve()
    if target.is_relative_to(ROOT):raise ValueError('Archive must be outside project tree')
    report=audit();(ROOT/'docs/evidence/delivery-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    entries=files();inventory={str(f.relative_to(ROOT)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in entries}
    target.parent.mkdir(parents=True,exist_ok=True)
    archive_manifest=json.dumps({'files':inventory,'physical_hardware_tests':0,'remote_github_created':False},indent=2)+'\n'
    (ROOT/'DELIVERY-MANIFEST.json').write_text(archive_manifest)
    temporary=target.with_name(target.name+'.partial')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in entries:z.write(f,'codex-glasses/'+str(f.relative_to(ROOT)))
        z.writestr('codex-glasses/DELIVERY-MANIFEST.json',archive_manifest)
    with zipfile.ZipFile(temporary) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise RuntimeError('Duplicate ZIP entry')
        if z.testzip():raise RuntimeError('ZIP CRC failure')
        for rel,meta in inventory.items():
            if hashlib.sha256(z.read('codex-glasses/'+rel)).hexdigest()!=meta['sha256']:raise RuntimeError('ZIP readback differs: '+rel)
    os.replace(temporary,target)
    print(json.dumps({'archive':str(target),'project_files':len(entries),'zip_bytes':target.stat().st_size,'sha256':sha(target),'readback_verified':True},indent=2))


if __name__=='__main__':main()
