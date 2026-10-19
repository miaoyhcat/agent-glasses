#!/usr/bin/env python3
"""Build dependency-free native Android app using the official SDK, without Gradle.

Requires JDK >=17, platform android-35 and build-tools 35.0.0. Creates a debug
certificate in scratch build/, never a production signing identity.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--sdk",type=Path,default=os.environ.get("ANDROID_SDK_ROOT"));p.add_argument("--out",type=Path,default=ROOT/"build/android")
    args=p.parse_args()
    if args.sdk is None:p.error("Set ANDROID_SDK_ROOT or pass --sdk")
    sdk=Path(args.sdk); tools=sdk/"build-tools/35.0.0"; jar=sdk/"platforms/android-35/android.jar"
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True);classes=out/"classes";classes.mkdir(exist_ok=True)
    source=ROOT/"mobile/android/app/src/main"
    # Gradle injects namespace; the direct SDK route uses a generated manifest.
    import xml.etree.ElementTree as ET
    ET.register_namespace('android','http://schemas.android.com/apk/res/android')
    manifest=ET.parse(source/"AndroidManifest.xml");manifest.getroot().set('package','dev.codexglasses')
    generated=out/"AndroidManifest.xml";manifest.write(generated,encoding='utf-8',xml_declaration=True)
    run([tools/"aapt2","link","-o",out/"base.apk","-I",jar,"--manifest",generated,"--min-sdk-version","26","--target-sdk-version","35","--version-code","2","--version-name","0.2.0"])
    compiler=["javac"] if shutil.which("javac") else ["java","com.sun.tools.javac.Main"]
    bootclasspath=str(jar)+os.pathsep+str(tools/"core-lambda-stubs.jar")
    run([*compiler,"-source","8","-target","8","-encoding","UTF-8","-bootclasspath",bootclasspath,"-d",classes,*sorted(source.glob("java/**/*.java"))])
    # d8 accepts archives, not arbitrary directory inputs.
    classjar=out/"classes.jar"
    with zipfile.ZipFile(classjar,"w") as z:
        for f in sorted(classes.rglob("*.class")):z.write(f,str(f.relative_to(classes)))
    run([tools/"d8","--lib",jar,"--min-api","26","--output",out,classjar])
    unsigned=out/"unsigned.apk";shutil.copyfile(out/"base.apk",unsigned)
    with zipfile.ZipFile(unsigned,"a",compression=zipfile.ZIP_DEFLATED) as z:z.write(out/"classes.dex","classes.dex")
    run([tools/"zipalign","-f","4",unsigned,out/"aligned.apk"])
    key=out/"debug.jks"
    if not key.exists():
        run(["keytool","-genkeypair","-keystore",key,"-storepass","android","-alias","debug","-keypass","android","-dname","CN=CodexGlasses Engineering Debug","-keyalg","RSA","-keysize","2048","-validity","3650"])
    result=out/"codexglasses-debug.apk"
    run([tools/"apksigner","sign","--ks",key,"--ks-pass","pass:android","--key-pass","pass:android","--out",result,out/"aligned.apk"])
    run([tools/"apksigner","verify","--verbose",result]);print(result)


if __name__=="__main__":main()
