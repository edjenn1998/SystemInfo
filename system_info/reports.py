"""Shared, Qt-independent privacy and atomic report export."""
import copy
import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path

from .core import CategoryResult, Field, SystemSnapshot

SENSITIVE = ('serial', 'uuid', 'hostname', 'nodename', 'username', 'fqdn', 'ipv4',
             'ipv6', 'macaddress', 'gateway', 'host', 'terminal', 'dns', 'mountpoint',
             'productsku', 'asset', 'ssid', 'servicetag', 'fstab', 'filesystemlabel',
             'partlabel', 'password', 'credential', 'secret', 'token')
ALIASES = {'hw', 'gw', 'ip', 'ips', 'mac', 'bssid', 'essid', 'address', 'addresses',
           'ipaddress', 'ipaddresses', 'hardwareaddress', 'loginname', 'uid', 'gid', 'uidgid', 'userid', 'groupid'}
MAC = re.compile(r'(?<![\w:])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![\w:])', re.I)
IP = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?<![\w:])[0-9a-f]*:[0-9a-f:]+(?:%[\w.-]+)?(?![\w:])', re.I)
USER_PATH = re.compile(r'/(?:home|Users)/[^/\s]+')


def sensitive(key):
    normalized = ''.join(c for c in str(key).casefold() if c.isalnum())
    return normalized in ALIASES or any(term in normalized for term in SENSITIVE)


def credential_safe(text):
    return re.sub(r'((?:[a-z][a-z0-9+.-]*:)?//)[^/\s@]+@', r'\1[credentials]@', text, flags=re.I)


def _sensitive_member(node, key):
    return sensitive(key) or (node.get('kind') in ('user', 'filesystem') and key == 'name')


def safe_report(data):
    """Redact structured identifiers recursively and their known copies in prose."""
    known = set()
    def remember(value):
        if isinstance(value, str) and len(value) >= 3 and value.casefold() not in ('unknown','not reported','unavailable','none','not specified','[hidden]'):
            known.add(value)
        elif isinstance(value, (list, tuple)):
            for member in value: remember(member)
        elif isinstance(value, dict):
            for member in value.values(): remember(member)
    def gather(value):
        if isinstance(value, dict):
            if 'label' in value and sensitive(value['label']): remember(value.get('value'))
            for key, member in value.items():
                if _sensitive_member(value, key): remember(member)
                gather(member)
        elif isinstance(value, (list, tuple)):
            for member in value: gather(member)
    gather(data)
    identifiers = sorted(known, key=len, reverse=True)
    known_pattern = re.compile('|'.join(re.escape(value) for value in identifiers), re.I) if identifiers else None

    def prose(text):
        if known_pattern is not None: text = known_pattern.sub('[hidden]', text)
        text = credential_safe(text)
        if text.startswith('//'): return '//[hidden]'
        text = re.sub(r'\b(?:smb|cifs|nfs|ssh|sftp)://\S+', '[hidden]', text, flags=re.I)
        text = MAC.sub('[hidden]', text)
        def hide_ip(match):
            try:
                ipaddress.ip_address(match[0].split('%', 1)[0])
                return '[hidden]'
            except ValueError:
                return match[0]
        return USER_PATH.sub('/home/[hidden]', IP.sub(hide_ip, text))

    def clean(value):
        if isinstance(value, dict):
            category = 'fields' in value and 'records' in value
            field = 'label' in value and 'value' in value
            result = {}
            for key, member in value.items():
                if _sensitive_member(value, key) or (field and key == 'value' and sensitive(value['label'])):
                    result[key] = copy.deepcopy(member) if member is None or member == '' or member == [] or member == {} else '[hidden]'
                elif key in ('kind', 'unit', 'advanced', 'advanced_keys', 'schema_version', 'app_version') or (category and key in ('name', 'title')) or (field and key == 'label'):
                    result[key] = copy.deepcopy(member)
                else:
                    result[key] = clean(member)
            return result
        if isinstance(value, (list, tuple)):
            return [clean(member) for member in value]
        return prose(value) if isinstance(value, str) else value
    return clean(data)


def report_data(snapshot, private=True):
    data = snapshot.to_dict()
    if private:
        data = safe_report(data)
    else:
        def clean(value):
            if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
            if isinstance(value, list): return [clean(v) for v in value]
            return credential_safe(value) if isinstance(value, str) else value
        data = clean(data)
    data['privacy'] = {'identifiers_hidden': private,
                       'note': 'Known identifiers are hidden; vendor-supplied free-form text is not guaranteed anonymous.' if private else 'Identifying details included.'}
    return data


def render_report(snapshot, format='json', private=True, color=False):
    data = report_data(snapshot, private)
    if format == 'json':
        return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if format != 'text': raise ValueError('Report format must be json or text')
    from .renderers.text import ConsoleRenderer
    sanitized = SystemSnapshot(captured_at=data['collected_at'])
    for category in data['categories']:
        sanitized.add(CategoryResult(category['name'], category['title'],
            [Field(**value) for value in category['fields']], category['records'], category.get('note')))
    return ('System Info ' + data['app_version'] + ' • ' + data['collected_at'] + '\n' +
            data['privacy']['note'] + '\n' + ConsoleRenderer(color=color).render(sanitized) + '\n')


def write_report(path, text):
    path = Path(path).expanduser()
    fd, name = tempfile.mkstemp(prefix='.system-info-report-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
