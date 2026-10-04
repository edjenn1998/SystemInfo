"""Filesystem identifiers and safe fstab associations (never export credentials)."""
import glob
import re
from pathlib import Path
from .collectors.base import read_file

def unescape_fstab(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)

def parse_fstab(text):
    result=[]
    for line in (text or '').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        fields=line.split()
        if len(fields)<3:continue
        # Mount options can contain passwords. Keep only source, target and type.
        source,target,filesystem=[unescape_fstab(f) for f in fields[:3]]
        result.append({'source':source,'mountpoint':target,'filesystem':filesystem})
    return result

def match_fstab(device,entries):
    result=[]
    for entry in entries:
        source=entry['source'];key,sep,value=source.partition('=');value=value.strip('"')
        match=False
        if sep and key in ('UUID','PARTUUID'):
            ident=device.get('uuid' if key=='UUID' else 'partuuid')
            match=bool(ident and str(ident).casefold()==value.casefold())
        elif sep and key=='LABEL':match=bool(device.get('label') and device['label']==value)
        elif source==device.get('path'):match=True
        elif source.startswith('/dev/disk/by-uuid/'):
            match=bool(device.get('uuid') and source.rsplit('/',1)[-1].casefold()==str(device['uuid']).casefold())
        elif source.startswith('/dev/disk/by-partuuid/'):
            match=bool(device.get('partuuid') and source.rsplit('/',1)[-1].casefold()==str(device['partuuid']).casefold())
        if match:result.append(f'{source} → {entry["mountpoint"]} ({entry["filesystem"]})')
    return result

def device_aliases():
    result={}
    for folder,key in [('by-uuid','uuid'),('by-partuuid','partuuid'),('by-label','label')]:
        for path in glob.glob('/dev/disk/'+folder+'/*'):
            try:device=str(Path(path).resolve(strict=True))
            except (OSError,RuntimeError):continue
            result.setdefault(device,{})[key]=Path(path).name
    return result
