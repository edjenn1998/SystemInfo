"""Explicit read-only hardware access through the desktop authorization agent.

Only trusted system executables are run with privilege. The GUI and bundled
Python executable never run as root. No shell, passwords, or temporary scripts.
"""
import json
import os
import re
import subprocess
import shutil
import stat
from pathlib import Path
from .smbios import parse_smbios

def trusted_tool(name, paths):
    # Distro-neutral discovery, but never elevate a user-controlled PATH binary.
    basename=Path(paths[0]).name
    candidates=[*paths,'/run/current-system/sw/bin/'+basename]
    found=shutil.which(basename)
    if found:candidates.append(found)
    for path in candidates:
        p=Path(path)
        try:
            resolved=p.resolve(strict=True)
            if not resolved.is_file() or not os.access(resolved,os.X_OK):continue
            chain=[resolved,*resolved.parents]
            if any(item.stat().st_uid!=0 or item.stat().st_mode & (stat.S_IWGRP|stat.S_IWOTH) for item in chain):continue
            return str(resolved)
        except (OSError,RuntimeError):continue
    raise RuntimeError(f'{name} is not installed in a trusted system location on this computer.')

def read_protected(action, device=None):
    pkexec=trusted_tool('Desktop authorization (pkexec)',['/usr/bin/pkexec','/bin/pkexec'])
    if action=='firmware':
        cat=trusted_tool('cat',['/usr/bin/cat','/bin/cat'])
        args=[pkexec,cat,'/sys/firmware/dmi/tables/DMI']
    elif action=='smart':
        if not device or not re.fullmatch(r'/dev/(?:nvme\d+n\d+|sd[a-z]+|hd[a-z]+|mmcblk\d+|vd[a-z]+)',device):
            raise RuntimeError('Select a supported physical drive from the live inventory.')
        smartctl=trusted_tool('smartctl (smartmontools)',['/usr/sbin/smartctl','/sbin/smartctl','/usr/bin/smartctl'])
        args=[pkexec,smartctl,'-j','-a',device]
    else:raise ValueError('Unsupported protected operation')
    try:proc=subprocess.run(args,capture_output=True,timeout=120)
    except subprocess.TimeoutExpired:raise RuntimeError('Authorization or hardware read timed out.')
    if proc.returncode in (126,127):raise RuntimeError('Authorization was cancelled or denied. The normal report remains available.')
    if action=='firmware':
        if proc.returncode==0:return parse_smbios(proc.stdout)
        # Older kernels and some distributions expose SMBIOS only through dmidecode.
        decoder=trusted_tool('dmidecode (firmware fallback)',['/usr/sbin/dmidecode','/sbin/dmidecode','/usr/bin/dmidecode'])
        from .inventory import DMI_TYPES,dmi_sections
        try:fallback=subprocess.run([pkexec,decoder,'--type',DMI_TYPES],capture_output=True,timeout=120)
        except subprocess.TimeoutExpired:raise RuntimeError('The firmware fallback timed out.')
        if fallback.returncode in (126,127):raise RuntimeError('Firmware authorization was cancelled or denied.')
        sections=dmi_sections(fallback.stdout.decode('utf-8',errors='replace'))
        if fallback.returncode!=0 or not sections:raise RuntimeError('This machine did not expose readable firmware inventory.')
        return sections
    try:data=json.loads(proc.stdout)
    except (ValueError,UnicodeDecodeError):raise RuntimeError('The drive did not return a readable SMART report.')
    if not any(k in data for k in ('smart_status','nvme_smart_health_information_log','ata_smart_attributes')):
        raise RuntimeError('SMART information is not available for this drive or its connection.')
    return data
