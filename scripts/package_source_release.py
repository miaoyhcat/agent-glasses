#!/usr/bin/env python3
"""Create a GitHub-ready source ZIP and a self-contained, verified Git bundle.

Uses an isolated temporary Git repository. Never changes a caller's Git history,
creates a remote repository, reads credentials or pushes without a separate user
operation. Compiled-source and existing artifact hashes are audited first.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args,cwd,environment):
    process=subprocess.run(args,cwd=cwd,env=environment,capture_output=True,text=True)
    if process.returncode:raise RuntimeError('Command failed: '+args[0]+' '+args[1]+'\n'+process.stderr[-2000:])
    return process.stdout.strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tag',default='v0.2.0-source.1')
    args=parser.parse_args();target=args.output.resolve()
    if target.is_relative_to(ROOT):raise ValueError('Output must be outside the project directory')
    if not re.fullmatch(r'v[0-9A-Za-z._-]{1,80}',args.tag):raise ValueError('Invalid release tag')
    if not shutil.which('git'):raise RuntimeError('Git is required')
    spec=importlib.util.spec_from_file_location('codexglasses_delivery_audit',ROOT/'scripts/package_delivery.py')
    delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)
    comparison=json.loads((ROOT/'docs/product-comparison.json').read_text())
    sources=json.loads((ROOT/'docs/sources.json').read_text());source_ids={row['id'] for row in sources}
    if len(comparison)!=8:raise RuntimeError('Expected CodexGlasses and seven representative products')
    for row in comparison:
        if row['sources']!='PROJECT' and not set(row['sources'].split('|'))<=source_ids:
            raise RuntimeError('Unresolved comparison source')
    required_notice='本项目仅允许个人非商业学习、研究、修改及自用。'
    if required_notice not in (ROOT/'README.md').read_text()[:1500]:raise RuntimeError('Prominent Chinese license notice missing')
    if 'Personal noncommercial use only' not in (ROOT/'README_EN.md').read_text()[:1500]:raise RuntimeError('Prominent English license notice missing')
    if '3277681859@qq.com' not in (ROOT/'COMMERCIAL-LICENSE.md').read_text():raise RuntimeError('Commercial contact missing')
    for path in ['assets/codexglasses-banner.svg','docs/design-index.md','COMMERCIAL-LICENSE.md','CONTRIBUTING.md','CHANGELOG.md']:
        if not (ROOT/path).is_file():raise RuntimeError('Publication file missing: '+path)
    import xml.etree.ElementTree as ET
    ET.parse(ROOT/'assets/codexglasses-banner.svg')
    (ROOT/'docs/evidence/publication-validation.json').write_text(json.dumps({'release_tag':args.tag,'status':'publication_documents_checked','comparison_source_ids_resolve':True,'prominent_licensing_verified':True,'banner_xml_valid':True},indent=2)+'\n')
    audit=delivery.audit()
    audit.update(publication_comparison_rows=len(comparison),prominent_licensing_verified=True)
    (ROOT/'docs/evidence/delivery-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    publication={
        'evidence_level':2,'generated_utc':datetime.now(timezone.utc).isoformat(),
        'release_tag':args.tag,'software_version':'0.2.0','publication_scope':'Documentation, source organization, comparison and local Git distribution',
        'runtime_build_input_hashes_match':True,'tested_apk_hash_matches':True,'tested_wheel_hash_matches':True,
        'vendor_source_hashes_match':True,'comparison_source_ids_resolve':True,'comparison_rows':len(comparison),
        'market_database_products':len(json.loads((ROOT/'docs/market-database.json').read_text())),
        'source_references':len(sources),'recorded_host_tests':audit['host_test_count'],
        'historical_package_readback':'docs/evidence/package-readback.json records the v0.2 engineering archive; publication documentation changes are separately scoped here',
        'physical_hardware_tests':0,'remote_github_created':False,
        'license':'LicenseRef-CodexGlasses-Personal-Noncommercial-1.0','commercial_contact':'3277681859@qq.com'}
    (ROOT/'docs/evidence/publication-validation.json').write_text(json.dumps(publication,indent=2)+'\n')
    (ROOT/'SOURCE-RELEASE.json').write_text(json.dumps({'release_tag':args.tag,'software_version':'0.2.0',
        'license':'LicenseRef-CodexGlasses-Personal-Noncommercial-1.0','commercial_contact':'3277681859@qq.com',
        'design_index':'docs/design-index.md','product_comparison':'docs/product-comparison.md',
        'validation':'docs/evidence/publication-validation.json'},indent=2)+'\n')
    # Historical archives keep their own recorded hashes. Current manifest covers
    # this publication snapshot; the manifest cannot hash itself recursively.
    entries=delivery.files()
    inventory={str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in entries}
    manifest=ROOT/'DELIVERY-MANIFEST.json'
    manifest.write_text(json.dumps({'files':inventory,'physical_hardware_tests':0,'remote_github_created':False},indent=2)+'\n')
    entries.append(manifest)
    hashes={str(p.relative_to(ROOT)):sha(p) for p in entries}
    build=ROOT/'build';build.mkdir(exist_ok=True);target.parent.mkdir(parents=True,exist_ok=True)
    environment={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull}
    # The commit identity describes the packaging process, not a legal owner.
    environment.update(GIT_AUTHOR_NAME='CodexGlasses packaging automation',GIT_AUTHOR_EMAIL='build@codexglasses.invalid',
                       GIT_COMMITTER_NAME='CodexGlasses packaging automation',GIT_COMMITTER_EMAIL='build@codexglasses.invalid')
    with tempfile.TemporaryDirectory(prefix='codexglasses-source-release-',dir=build) as temporary:
        temporary=Path(temporary);snapshot=temporary/'snapshot';snapshot.mkdir()
        for path in entries:
            rel=path.relative_to(ROOT);copy=snapshot/rel;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,copy)
            if sha(copy)!=hashes[str(rel)]:raise RuntimeError('Snapshot copy mismatch: '+str(rel))
        run(['git','init','-b','main'],snapshot,environment)
        run(['git','config','core.autocrlf','false'],snapshot,environment)
        run(['git','config','commit.gpgsign','false'],snapshot,environment)
        run(['git','add','--force','--all'],snapshot,environment)
        run(['git','commit','-m','Publish CodexGlasses source, design files, use policy and product comparison'],snapshot,environment)
        run(['git','tag',args.tag],snapshot,environment)
        commit=run(['git','rev-parse','HEAD'],snapshot,environment)
        tracked=[p for p in run(['git','ls-files','-z'],snapshot,environment).split('\0') if p]
        if set(tracked)!=set(hashes):raise RuntimeError('Git index does not contain the exact publication snapshot')
        bundle=temporary/'codex-glasses.git.bundle'
        run(['git','bundle','create',str(bundle),'--all'],snapshot,environment)
        verified=run(['git','bundle','verify',str(bundle)],snapshot,environment)
        clone=temporary/'clone'
        run(['git','clone','--branch','main',str(bundle),str(clone)],temporary,environment)
        if run(['git','rev-parse','HEAD'],clone,environment)!=commit:raise RuntimeError('Bundle clone commit differs')
        for path,digest in hashes.items():
            if sha(clone/path)!=digest:raise RuntimeError('Bundle clone content differs: '+path)
        # Re-run the artifact/content audit from the independently cloned files.
        clone_spec=importlib.util.spec_from_file_location('codexglasses_clone_audit',clone/'scripts/package_delivery.py')
        clone_audit=importlib.util.module_from_spec(clone_spec);clone_spec.loader.exec_module(clone_audit)
        clone_audit.audit()
        package_info={'project':'CodexGlasses','release_tag':args.tag,'commit':commit,'branch':'main',
            'tracked_project_files':len(hashes),'git_bundle_verified':True,'offline_clone_verified':True,
            'clone_file_hashes_match':True,'source_archive_readback_verified':True,'remote_github_created':False,
            'bundle_sha256':sha(bundle),'software_version':'0.2.0','comparison_products':len(comparison),
            'source_references':len(sources),'commercial_contact':'3277681859@qq.com',
            'license':'LicenseRef-CodexGlasses-Personal-Noncommercial-1.0'}
        first='''# CodexGlasses GitHub source release\n\n个人非商业学习、研究、修改及自用；商业销售、生产销售、集成或授权须事先取得书面许可。商业授权：3277681859@qq.com。完整条款在codex-glasses/LICENSE。\n\n- codex-glasses/：完整可浏览源码与设计资料，先看README.md和docs/design-index.md。\n- codex-glasses.git.bundle：已验证的自包含Git仓库，含main分支与发布标签。\n- REPOSITORY-INFO.json：提交、离线克隆、文件哈希和授权信息。\n\n在此目录执行：\n\n```bash\ngit clone ./codex-glasses.git.bundle ./codex-glasses-git\n```\n\n然后按codex-glasses-git/scripts/publish-github.md推送到自己的GitHub公开仓库。仓库首页包含授权说明与同类产品对比。\n'''
        partial=target.with_name(target.name+'.partial')
        run(['git','archive','--format=zip','--prefix=codex-glasses/','--output='+str(partial),'HEAD'],snapshot,environment)
        with zipfile.ZipFile(partial,'a',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            z.write(bundle,'codex-glasses.git.bundle')
            z.writestr('REPOSITORY-INFO.json',json.dumps(package_info,indent=2)+'\n')
            z.writestr('START_HERE.md',first)
        with zipfile.ZipFile(partial) as z:
            if len(z.namelist())!=len(set(z.namelist())) or z.testzip():raise RuntimeError('ZIP integrity failed')
            for path,digest in hashes.items():
                if hashlib.sha256(z.read('codex-glasses/'+path)).hexdigest()!=digest:raise RuntimeError('ZIP source differs: '+path)
            if hashlib.sha256(z.read('codex-glasses.git.bundle')).hexdigest()!=package_info['bundle_sha256']:raise RuntimeError('ZIP bundle differs')
        os.replace(partial,target)
    print(json.dumps({**package_info,'archive':str(target),'zip_bytes':target.stat().st_size,'archive_sha256':sha(target)},indent=2))


if __name__=='__main__':main()
