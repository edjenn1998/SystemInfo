"""Deterministic memory calculations: no hardware access or authorization."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from system_info.collectors.memory import (
    MemoryCollector, installed_capacity, memory_inventory, memory_usage,
    smbios_capacity_bytes, unavailable_memory,
)

GIB = 1024**3


def inventory(sizes=('8192 MB', '8192 MB'), count='2', correction='Unknown'):
    return [dict(type=16, handle='0x10', fields={
        'Use': 'System Memory', 'Number Of Devices': count,
        'Error Correction Type': correction,
    })] + [dict(type=17, handle=f'0x{32+i:x}', fields={
        'Array Handle': '0x10', 'Size': size, 'Locator': f'DIMM_{i}',
        'Type': 'DDR4', 'Manufacturer': 'Example', 'Part Number': 'TEST-123',
        'Speed': '3200 MT/s', 'Configured Memory Speed': '2666 MT/s',
        'Total Width': '72 bits', 'Data Width': '64 bits',
    }) for i, size in enumerate(sizes)]


def collect(sections=None, meminfo=None, status='available'):
    vm = SimpleNamespace(total=99*GIB, available=4*GIB)
    sw = SimpleNamespace(total=2*GIB, used=GIB//2, free=3*GIB//2, percent=25)
    if meminfo is None:
        meminfo = {'MemTotal': 15*1024**2, 'MemAvailable': 5*1024**2}
    with patch('system_info.collectors.memory.psutil.virtual_memory', return_value=vm), \
         patch('system_info.collectors.memory.psutil.swap_memory', return_value=sw), \
         patch('system_info.collectors.memory._parse_meminfo', return_value=meminfo), \
         patch.object(MemoryCollector, '_dimm_slots', return_value=[]):
        return MemoryCollector(context={'dmi_sections': sections or [], 'dmi_status': status}).collect()


class MemoryTests(unittest.TestCase):
    def fields(self, result):
        return {field.label: field.value for field in result.fields}

    def test_smbios_binary_units(self):
        for value in ('16384 MB', '16384 MiB', '16 GB', '16 GiB', '16777216 kB'):
            with self.subTest(value=value):
                self.assertEqual(smbios_capacity_bytes(value), 16*GIB)
        self.assertNotEqual(smbios_capacity_bytes('16 GB'), 16*10**9)
        self.assertEqual(smbios_capacity_bytes('1 TB'), 1024*GIB)
        self.assertEqual(smbios_capacity_bytes('1 KiB'), 1024)

    def test_unknown_invalid_sizes(self):
        for value in ('Unknown', None, '', '-1 GB', 'NaN MB', '16 XB', '1.5 GB'):
            with self.subTest(value=value):
                self.assertIsNone(smbios_capacity_bytes(value))

    def test_realistic_capacity_and_procfs_usage(self):
        fields = self.fields(collect(inventory()))
        self.assertEqual(fields['Installed RAM'], 16)
        self.assertEqual(fields['Usable RAM'], 15)  # not psutil fixture's 99 GiB
        self.assertEqual(fields['Unavailable to Linux'], 1)
        self.assertEqual(fields['RAM in use'], 10)
        self.assertEqual(fields['RAM available'], 5)
        self.assertEqual(fields['RAM usage'], 66.7)
        self.assertEqual(fields['Swap available'], 1.5)

    def test_unavailable_exact_bytes_before_rounding(self):
        self.assertEqual(unavailable_memory(16*GIB, 16*GIB-1024), 1024)
        self.assertEqual(unavailable_memory(16*GIB, 16*GIB), 0)

    def test_inconsistent_capacity_never_negative(self):
        result = self.fields(collect(inventory(('8192 MB',), '1')))
        self.assertEqual(result['Unavailable to Linux'], 'Not available')
        self.assertIn('below Linux', result['Capacity validation'])
        self.assertIsNone(unavailable_memory(8*GIB, 15*GIB))

    def test_missing_firmware_all_access_states(self):
        for status in ('authorization_required', 'interface_absent', 'not_reported', 'read_failed'):
            with self.subTest(status=status):
                fields = self.fields(collect(status=status))
                self.assertEqual(fields['Installed RAM'], 'Not available')
                self.assertEqual(fields['Unavailable to Linux'], 'Not available')
                self.assertEqual(fields['Usable RAM'], 15)

    def test_incomplete_inventory(self):
        fields = self.fields(collect(inventory(('8192 MB',), '4')))
        self.assertEqual(fields['Installed RAM'], 'Not available')
        self.assertEqual(fields['Reported module capacity (incomplete inventory)'], 8)

    def test_unknown_module_capacity(self):
        self.assertEqual(self.fields(collect(inventory(('8192 MB', 'Unknown'))))['Installed RAM'], 'Not available')

    def test_empty_devices_are_not_capacity(self):
        sections = inventory(('16384 MB', 'No Module Installed'))
        fields = self.fields(collect(sections))
        self.assertEqual(fields['Installed RAM'], 16)
        self.assertEqual(fields['Banks empty'], 1)

    def test_module_only_inventory_is_partial(self):
        sections = inventory()[1:]
        fields = self.fields(collect(sections))
        self.assertEqual(fields['Installed RAM'], 'Not available')
        self.assertEqual(fields['Reported module capacity (incomplete inventory)'], 16)
        self.assertNotIn('Memory banks reported', fields)

    def test_zero_unknown_counts_and_sizes(self):
        for count in ('0', 'Unknown', ''):
            self.assertEqual(self.fields(collect(inventory(count=count)))['Installed RAM'], 'Not available')
        count, _, _, _, modules = memory_inventory(inventory(('0 MB', '0 GB')))
        self.assertEqual(installed_capacity(count, modules), (None, 0))

    def test_duplicate_devices_rejected(self):
        sections = inventory()
        sections[2]['handle'] = sections[1]['handle']
        self.assertEqual(self.fields(collect(sections))['Installed RAM'], 'Not available')

    def test_per_array_mismatch_not_hidden_by_aggregate(self):
        sections = inventory()
        sections[0]['fields']['Number Of Devices'] = '1'
        sections.append(dict(type=16, handle='0x11', fields={'Use': 'System Memory', 'Number Of Devices': '1'}))
        self.assertEqual(self.fields(collect(sections))['Installed RAM'], 'Not available')

    def test_available_clamped_and_old_kernel_fallback(self):
        vm = SimpleNamespace(available=GIB)
        self.assertEqual(memory_usage({'MemTotal': 2*1024**2}, vm), (2*GIB, GIB, GIB, 50))
        self.assertEqual(memory_usage({'MemTotal': 1, 'MemAvailable': 2}, vm), (1024, 0, 1024, 0))
        self.assertEqual(memory_usage({'MemTotal': 1, 'MemAvailable': 0}, vm), (1024, 1024, 0, 100))
        self.assertEqual(memory_usage({}, vm), (None, None, None, None))
        self.assertEqual(memory_usage({'MemTotal': 0}, vm), (None, None, None, None))

    def test_missing_procfs_does_not_invent_usable(self):
        fields = self.fields(collect(inventory(), meminfo={}))
        self.assertEqual(fields['Usable RAM'], 'Not available')
        self.assertEqual(fields['Unavailable to Linux'], 'Not available')

    def test_speeds_distinct_and_timings_never_from_profiles(self):
        sections = inventory()
        sections[1]['fields']['CAS Latency'] = '16'  # not an active source
        fields = self.fields(collect(sections))
        self.assertEqual(fields['Configured speed'], '2666 MT/s')
        self.assertEqual(fields['Rated speed (firmware maximum)'], '3200 MT/s')
        for label in ('CAS Latency (tCL)', 'RAS to CAS Delay (tRCD)', 'Row Precharge (tRP)',
                      'Active to Precharge Delay (tRAS)', 'Command Rate'):
            self.assertEqual(fields[label], 'Not available')
        self.assertFalse(any('channel' in label.lower() for label in fields))

    def test_ecc_requires_array_and_width_evidence(self):
        modules = memory_inventory(inventory(correction='Single-bit ECC'))[-1]
        self.assertIn('ECC-capable', modules[0]['ecc_capability'])
        modules = memory_inventory(inventory(correction='Parity'))[-1]
        self.assertEqual(modules[0]['ecc_capability'], 'Not available')
        sections = inventory(correction='Multi-bit ECC')
        sections[1]['fields']['Total Width'] = '64 bits'
        self.assertEqual(memory_inventory(sections)[-1][0]['ecc_capability'], 'Not available')

    def test_module_metadata(self):
        module = collect(inventory()).records[0]
        self.assertEqual(module['name'], 'DIMM_0')
        self.assertEqual(module['manufacturer'], 'Example')
        self.assertEqual(module['part_number'], 'TEST-123')
        self.assertEqual(module['memory_type'], 'DDR4')

    def test_tooltips_exported_with_sections(self):
        fields = collect(inventory()).to_dict()['fields']
        unavailable = next(f for f in fields if f['label'] == 'Unavailable to Linux')
        self.assertEqual(unavailable['section'], 'System Memory')
        self.assertIn('integrated GPU', unavailable['tooltip'])

    def test_edac_standard_size_and_missing_label(self):
        values = {'size': '16384', 'dimm_mem_type': 'Unbuffered-DDR4', 'dimm_edac_mode': 'SECDED'}
        with patch('system_info.collectors.memory.glob.glob', return_value=['/sys/fake/dimm0']), \
             patch('system_info.collectors.memory.read_file', side_effect=lambda p: values.get(p.rsplit('/', 1)[-1])):
            modules = MemoryCollector()._dimm_slots()
        self.assertEqual(modules[0]['size'], '16384')
        self.assertEqual(modules[0]['name'], 'dimm0')
        self.assertEqual(modules[0]['memory_type'], 'Unbuffered-DDR4')

    def test_smbios_array_ecc_decode(self):
        from system_info.smbios import parse_smbios
        blob = bytearray(15)
        blob[0] = 16; blob[1] = 15; blob[5] = 3; blob[6] = 6; blob[13] = 2
        sections = parse_smbios(bytes(blob) + b'\0\0')
        self.assertEqual(sections[0]['fields']['Error Correction Type'], 'Multi-bit ECC')


if __name__ == '__main__':
    unittest.main()
