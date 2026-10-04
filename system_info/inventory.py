"""Read-only shared inventory helpers. Firmware text is cached for one collection."""
import re
from pathlib import Path
from .collectors.base import read_file, run_cmd

DMI_TYPES = '0,1,2,3,4,16,17'
UNKNOWN = {'', 'unknown', 'not specified', 'not provided', 'none', 'to be filled by o.e.m.', 'default string'}

def meaningful(value):
    return value if value is not None and str(value).strip().lower() not in UNKNOWN else None

def dmi_sections(text):
    sections = []
    current = None
    for line in (text or '').splitlines():
        match = re.match(r'Handle\s+\S+,\s+DMI type\s+(\d+)', line)
        if match:
            current = {'type': int(match.group(1)), 'handle':line.split(',')[0].split()[1].lower(), 'fields': {}}
            sections.append(current)
        elif current is not None and line[:1].isspace() and ':' in line:
            key, value = line.strip().split(':', 1)
            current['fields'][key] = value.strip()
    return sections

def get_dmi(context):
    # App supplies this before worker threads start; no concurrent mutation.
    return context['dmi_sections'] if 'dmi_sections' in context else dmi_sections(context.get('dmi_text') or '')

def numeric(path):
    value = read_file(str(path))
    try: return float(value) if value is not None else None
    except ValueError: return None

def capacity_label(size):
    if size is None: return 'Not reported'
    size = int(size)
    decimal = f'{size / 10**12:.2f} TB' if size >= 10**12 else f'{size / 10**9:.1f} GB'
    return f'{decimal} ({size / 1024**3:.1f} GiB)'

def clean_fields(mapping):
    return {key: value for key, value in mapping.items() if meaningful(value) is not None}
