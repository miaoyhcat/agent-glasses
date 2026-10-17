#!/usr/bin/env python3
"""Decode the D0 losslessly stored JPEG-frame container. No ffmpeg dependency."""
import argparse
import csv
from pathlib import Path
import struct


def extract(source:Path,destination:Path):
    destination.mkdir(parents=True,exist_ok=True);frames=[]
    with source.open('rb') as f:
        if f.read(5)!=b'AGMJ1':raise ValueError('not an AgentGlass JPEG-frame recording')
        while header:=f.read(8):
            if len(header)!=8:raise ValueError('truncated frame header')
            timestamp,length=struct.unpack('<II',header)
            if not 4<=length<=2*1024*1024:raise ValueError('invalid frame length')
            jpeg=f.read(length)
            if len(jpeg)!=length or not jpeg.startswith(b'\xff\xd8'):raise ValueError('truncated or invalid JPEG frame')
            name=f'{len(frames):06d}.jpg';(destination/name).write_bytes(jpeg);frames.append({'file':name,'timestamp_ms':timestamp,'bytes':length})
    with (destination/'frames.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['file','timestamp_ms','bytes']);writer.writeheader();writer.writerows(frames)
    return frames


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    print('extracted frames:',len(extract(a.source,a.destination)))
