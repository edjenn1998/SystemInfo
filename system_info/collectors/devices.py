"""Human-facing connected devices; controller plumbing is technical detail."""
import re
from .base import Collector, run_cmd
class DevicesCollector(Collector):
    name='devices';title='Connected devices'
    def collect(self):
        r=self.new_result();count=0
        usb=run_cmd(['lsusb'])
        for line in (usb or '').splitlines():
            m=re.search(r'Bus (\d+) Device (\d+): ID ([0-9a-f]{4}:[0-9a-f]{4})\s+(.*)',line,re.I)
            if m:
                desc=m[4].strip();hub='root hub' in desc.lower() or bool(re.search(r'\bhub\b',desc,re.I))
                r.add_record({'kind':'usb_hub' if hub else 'usb_device','name':desc,'USB_ID':m[3],'bus':m[1],'device_number':m[2],'advanced':hub})
                if not hub:count+=1
        r.add('USB devices (excluding hubs)',count)
        for line in (run_cmd(['lspci','-nnk']) or '').splitlines():
            m=re.match(r'(\S+)\s+(.*?)\s+\[([0-9a-f]{4})\]:\s*(.*?)\s*\[([0-9a-f]{4}):([0-9a-f]{4})\]',line,re.I)
            if m:r.add_record({'kind':'internal_controller','name':m[4],'controller_type':m[2],'slot':m[1],'vendor_id':m[5],'device_id':m[6],'advanced':True})
        r.note='Includes built-in USB devices such as webcams, Bluetooth and fingerprint readers. Hubs and internal PCI controllers are shown with technical details.'
        if not usb:r.note+=' lsusb is not available.'
        return r
