import contextlib
import copy
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from system_info.app import SystemInfoApp
from system_info.cancellation import Cancelled, checkpoint, collection_scope
from system_info.collectors.base import Collector, read_file, run_cmd, system_environment
from system_info.collectors.memory import MemoryCollector, memory_inventory
from system_info.collectors.power import PowerCollector, battery_record
from system_info.collectors.storage import StorageCollector, health_fields, smart_report
from system_info.collectors.gpu import x11_modes
from system_info.core import CategoryResult, SystemSnapshot
from system_info.demo import example_snapshot
from system_info.main import main as cli_main
from system_info.protected import read_protected
from system_info.reports import report_data, render_report, safe_report, write_report
from system_info.smbios import parse_smbios


class ReportTests(unittest.TestCase):
    def test_nested_identifiers_are_hidden_without_changing_input(self):
        data = {'categories':[{'name':'memory','title':'Memory','fields':[], 'records':[
            {'kind':'memory_module','details':{'serial':'SERIAL-PRIVATE','uuid':None,'network':{'SSID':'Private WLAN','addresses':['192.0.2.15']}}}]}]}
        original = copy.deepcopy(data)
        result = safe_report(data)
        self.assertEqual(data, original)
        self.assertNotIn('SERIAL-PRIVATE', json.dumps(result))
        self.assertNotIn('Private WLAN', json.dumps(result))
        self.assertNotIn('192.0.2.15', json.dumps(result))
        self.assertIsNone(result['categories'][0]['records'][0]['details']['uuid'])

    def test_identifiers_copied_into_observations_are_hidden(self):
        cat = CategoryResult('storage','Storage')
        cat.add_record({'kind':'filesystem','name':'/mnt/Private Work','mountpoint':'/mnt/Private Work'})
        cat.add_record({'kind':'disk','uuid':'ABCD-1234'})
        cat.add_record({'kind':'observation','name':'Nearly full','detail':'/mnt/Private Work is 95% used; device abcd-1234'})
        snapshot = SystemSnapshot([cat])
        self.assertNotIn('/mnt/Private Work', render_report(snapshot))
        self.assertNotIn('abcd-1234', render_report(snapshot))

    def test_hostname_equal_to_category_does_not_break_schema(self):
        cat = CategoryResult('memory', 'Memory').add('Hostname', 'memory')
        result = report_data(SystemSnapshot([cat]))
        self.assertEqual(result['categories'][0]['name'], 'memory')
        self.assertEqual(result['categories'][0]['fields'][0]['label'], 'Hostname')
        self.assertEqual(result['categories'][0]['fields'][0]['value'], '[hidden]')

    def test_private_prose_hides_ips_mac_and_home_user(self):
        cat = CategoryResult('test','Test', note='192.0.2.55 2001:db8::1 aa:bb:cc:dd:ee:ff /home/private-user/file')
        result = render_report(SystemSnapshot([cat]))
        for value in ('192.0.2.55', '2001:db8::1', 'aa:bb:cc:dd:ee:ff', 'private-user'):
            self.assertNotIn(value, result)

    def test_include_identifiers_is_explicit_and_credentials_stay_removed(self):
        cat = CategoryResult('system','System').add('Hostname', 'PrivateHost')
        cat.add_record({'kind':'filesystem','device':'smb://alice:password@server/share'})
        result = render_report(SystemSnapshot([cat]), private=False)
        self.assertIn('PrivateHost', result)
        self.assertNotIn('alice:password', result)
        self.assertFalse(json.loads(result)['privacy']['identifiers_hidden'])

    def test_json_is_strict_with_nonfinite_values(self):
        cat = CategoryResult('test','Test').add('Invalid', math.nan)
        cat.add_record({'kind':'sensor','value':math.inf})
        result = json.loads(render_report(SystemSnapshot([cat])), parse_constant=lambda text: self.fail(text))
        self.assertIsNone(result['categories'][0]['fields'][0]['value'])
        self.assertIsNone(result['categories'][0]['records'][0]['value'])

    def test_text_and_json_apply_the_same_privacy(self):
        snapshot = example_snapshot()
        for format in ('json', 'text'):
            text = render_report(snapshot, format)
            self.assertIn('Example 8-core processor', text)
            self.assertNotIn('DEMO-SERIAL-PRIVATE', text)

    def test_failed_atomic_export_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'; path.write_text('previous report')
            with patch('system_info.reports.os.fsync', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): write_report(path, 'replacement')
            self.assertEqual(path.read_text(), 'previous report')
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_export_permissions_and_unicode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.txt'; write_report(path, '日本語\n')
            self.assertEqual(path.read_text(), '日本語\n')
            self.assertEqual(path.stat().st_mode & 0o077, 0)


class CollectionTests(unittest.TestCase):
    def test_empty_collection_does_not_probe_firmware(self):
        app = SystemInfoApp([])
        with patch.object(app, 'prepare_context') as prepare:
            self.assertEqual(app.collect_all().categories, [])
        prepare.assert_not_called()

    def test_cpu_only_does_not_probe_firmware(self):
        class Sample(Collector):
            name='cpu'; title='CPU'
            def collect(self): return self.new_result().add('test', 1)
        app = SystemInfoApp([Sample])
        with patch.object(app, 'prepare_context') as prepare:
            self.assertEqual(len(app.collect(['cpu']).categories), 1)
        prepare.assert_not_called()

    def test_parallel_results_keep_display_order(self):
        def make(name, delay):
            class Sample(Collector):
                def collect(self):
                    time.sleep(delay)
                    return self.new_result().add('value', name)
            Sample.name = name; Sample.title = name
            return Sample
        progress = []
        result = SystemInfoApp([make('first', .03), make('second', 0)]).collect_all(progress=lambda *args: progress.append(args))
        self.assertEqual([c.name for c in result.categories], ['overview','first','second'])
        self.assertEqual(len(progress), 2)

    def test_cancelled_collector_does_not_return_a_partial_success(self):
        token = threading.Event()
        class Sample(Collector):
            name='test'; title='Test'
            def collect(self):
                token.set(); checkpoint()
        with self.assertRaises(Cancelled): Sample(context={'cancel_event':token}).run()
        checkpoint()  # The thread-local token must have been reset.

    def test_cancel_after_last_progress_discards_snapshot(self):
        token = threading.Event()
        class Sample(Collector):
            name='test'; title='Test'
            def collect(self): return self.new_result().add('test', 1)
        with self.assertRaises(Cancelled):
            SystemInfoApp([Sample]).collect_all(cancel=token, progress=lambda *a: token.set())

    def test_overview_preserves_unknown_category_diagnostics(self):
        result = SystemInfoApp([]).collect(['overview','unknown'])
        self.assertEqual(result.get('unknown').note, 'unknown category')

    def test_file_decoding_replaces_bad_firmware_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'name'; path.write_bytes(b'Example\xff')
            self.assertIn('Example', read_file(str(path)))

    def test_command_timeout_terminates_owned_process(self):
        started = time.monotonic()
        self.assertIsNone(run_cmd([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.15))
        self.assertLess(time.monotonic()-started, 5)

    def test_command_can_be_cancelled(self):
        token = threading.Event(); timer = threading.Timer(.05, token.set); timer.start()
        try:
            with collection_scope(token):
                with self.assertRaises(Cancelled):
                    run_cmd([sys.executable, '-c', 'import time; time.sleep(30)'])
        finally:
            timer.cancel()

    def test_system_tools_do_not_inherit_bundled_libraries(self):
        with patch.object(sys, 'frozen', True, create=True), patch.dict(os.environ,
             {'LD_LIBRARY_PATH':'/bundle', 'LD_LIBRARY_PATH_ORIG':'/system', 'QT_PLUGIN_PATH':'/bundle/plugins'}):
            env = system_environment()
        self.assertEqual(env['LD_LIBRARY_PATH'], '/system')
        self.assertNotIn('QT_PLUGIN_PATH', env)
        self.assertEqual(env['LC_ALL'], 'C')

    def test_detached_pipe_holder_cannot_defeat_command_timeout(self):
        import signal
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / 'child.pid'
            script = ('import subprocess,sys,time; from pathlib import Path; '
                      'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],start_new_session=True); '
                      'Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)')
            started = time.monotonic()
            try:
                self.assertIsNone(run_cmd([sys.executable,'-c',script,str(pidfile)], timeout=.5))
                self.assertLess(time.monotonic()-started, 5)
            finally:
                if pidfile.exists():
                    try: os.kill(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass


class HardwareRegressionTests(unittest.TestCase):
    def battery(self, values):
        read = lambda path: values.get(str(path).rsplit('/', 1)[-1])
        with patch('system_info.inventory.read_file', side_effect=read), patch('system_info.collectors.power.read_file', side_effect=read):
            return battery_record('/sys/class/power_supply/BAT0')

    def test_energy_and_runtime_do_not_require_design_capacity(self):
        data = self.battery({'status':'Discharging','energy_full':'40000000','energy_now':'20000000','power_now':'10000000'})
        self.assertEqual(data['full_capacity_Wh'], 40)
        self.assertEqual(data['time_estimate'], '2h 0m remaining')
        self.assertNotIn('health_percent', data)

    def test_runtime_does_not_round_away_small_power_draw(self):
        data = self.battery({'status':'Discharging','energy_now':'4000','power_now':'4000'})
        self.assertEqual(data['time_estimate'], '1h 0m remaining')

    def test_energy_capacity_is_retained_when_health_uses_charge(self):
        data = self.battery({'energy_full':'40000000','charge_full':'4000000','charge_full_design':'5000000'})
        self.assertEqual(data['full_capacity_Wh'], 40)
        self.assertEqual(data['health_percent'], 80)

    def test_full_battery_does_not_override_offline_ac_reading(self):
        def read(path):
            return {'/fake/AC/type':'Mains','/fake/AC/online':'0','/fake/BAT/type':'Battery'}.get(path)
        with patch('system_info.collectors.power.glob.glob', return_value=['/fake/AC','/fake/BAT']), \
             patch('system_info.collectors.power.read_file', side_effect=read), \
             patch('system_info.inventory.read_file', side_effect=read), \
             patch('system_info.collectors.power.battery_record', return_value={'kind':'battery','status':'Full'}):
            fields = {f.label:f.value for f in PowerCollector().collect().fields}
        self.assertEqual(fields['Power source'], 'Battery')

    def test_non_system_memory_is_not_counted_as_ram(self):
        sections = [{'type':16,'handle':'0x10','fields':{'Use':'Video Memory','Number Of Devices':'1'}},
                    {'type':17,'fields':{'Array Handle':'0x10','Size':'8192 MB'}}]
        self.assertEqual(memory_inventory(sections)[-1], [])

    def test_incomplete_bank_inventory_does_not_claim_full_installed_capacity(self):
        sections = [{'type':16,'handle':'0x10','fields':{'Use':'System Memory','Number Of Devices':'4'}},
                    {'type':17,'fields':{'Array Handle':'0x10','Size':'8192 MB'}}]
        with patch.object(MemoryCollector, '_dimm_slots', return_value=[]):
            result = MemoryCollector(context={'dmi_sections':sections}).collect()
        values = {f.label:f.value for f in result.fields}
        self.assertNotIn('Installed RAM (firmware)', values)
        self.assertEqual(values['Reported module capacity (incomplete inventory)'], 8)

    def storage(self, rota):
        devices = [{'name':'sda','path':'/dev/sda','type':'disk','size':1000000000,'rota':rota}]
        with patch.object(StorageCollector, '_lsblk', return_value=devices), \
             patch('system_info.collectors.storage.smart_report', return_value={}), \
             patch('system_info.collectors.storage.device_aliases', return_value={}), \
             patch('system_info.collectors.storage.psutil.disk_partitions', return_value=[]), \
             patch('system_info.collectors.storage.glob.glob', return_value=[]):
            return next(r for r in StorageCollector().collect().records if r['kind']=='disk')

    def test_unknown_rotational_type_is_not_reported_as_ssd(self):
        self.assertNotIn('SSD', self.storage(None)['drive_type'])

    def test_string_zero_rotational_flag_is_not_reported_as_hdd(self):
        self.assertIn('SSD', self.storage('0')['drive_type'])

    def test_sysfs_fallback_preserves_unknown_rotational_type(self):
        with patch('system_info.collectors.storage.glob.glob', return_value=['/sys/class/block/sda']), \
             patch('system_info.collectors.storage.read_file', return_value=None), \
             patch('system_info.inventory.read_file', return_value=None):
            self.assertIsNone(StorageCollector()._sys_disks()[0]['rota'])

    def test_shared_volume_is_not_duplicated_and_lists_other_parent(self):
        child = {'path':'/dev/dm-0','type':'lvm'}
        devices = [{'path':'/dev/sda','children':[dict(child)]}, {'path':'/dev/sdb','children':[dict(child)]}]
        result = StorageCollector()._flatten_devices(devices)
        self.assertEqual(sum(d.get('path')=='/dev/dm-0' for d in result), 1)
        volume = next(d for d in result if d.get('path')=='/dev/dm-0')
        self.assertEqual(volume['other_parents'], ['/dev/sdb'])
        self.assertIn('children', devices[0])

    def test_remote_filesystem_space_query_is_skipped(self):
        remote = SimpleNamespace(device='server:/private',mountpoint='/mnt/net',fstype='nfs4')
        with patch.object(StorageCollector, '_lsblk', return_value=[{'name':'sda','path':'/dev/sda','type':'disk','size':1}]), \
             patch('system_info.collectors.storage.smart_report', return_value={}), \
             patch('system_info.collectors.storage.device_aliases', return_value={}), \
             patch('system_info.collectors.storage.psutil.disk_partitions', return_value=[remote]), \
             patch('system_info.collectors.storage.psutil.disk_usage') as usage:
            result = StorageCollector().collect()
        usage.assert_not_called()
        self.assertTrue(any(r.get('usage_note') for r in result.records))

    def test_smart_nonzero_health_bitmask_is_still_read(self):
        proc = subprocess.CompletedProcess([], 8, '{"smart_status":{"passed":false}}', '')
        with patch('system_info.collectors.storage.which', return_value='/usr/sbin/smartctl'), \
             patch('system_info.collectors.storage.run_process', return_value=proc):
            result = smart_report('/dev/sda', {})
        self.assertFalse(result['smart_status']['passed'])

    def test_smart_optional_null_sections_do_not_discard_other_metrics(self):
        result = health_fields({'smart_status':None,'temperature':{'current':45},'ata_smart_attributes':{'table':None}})
        self.assertEqual(result['Temperature (°C)'], 45)
        self.assertNotIn('SMART health', health_fields({'smart_status':{'passed':'false'}}))

    def test_protected_read_uses_clean_system_environment_and_fixed_args(self):
        with patch.object(sys,'frozen',True,create=True), patch.dict(os.environ, {'LD_LIBRARY_PATH':'/bundle'}), \
             patch('system_info.protected.trusted_tool', side_effect=['/usr/bin/pkexec','/usr/sbin/smartctl']), \
             patch('system_info.protected.subprocess.run', return_value=SimpleNamespace(returncode=8,stdout=b'{"smart_status":{"passed":false}}')) as run:
            data = read_protected('smart','/dev/sda')
        self.assertFalse(data['smart_status']['passed'])
        self.assertEqual(run.call_args.args[0], ['/usr/bin/pkexec','/usr/sbin/smartctl','-j','-a','/dev/sda'])
        self.assertNotEqual(run.call_args.kwargs['env'].get('LD_LIBRARY_PATH'), '/bundle')

    def test_invalid_protected_request_is_rejected_before_tool_lookup(self):
        with patch('system_info.protected.trusted_tool') as lookup:
            with self.assertRaises(RuntimeError): read_protected('smart','/dev/sda;bad')
            with self.assertRaises(ValueError): read_protected('write')
        lookup.assert_not_called()

    def test_valid_smart_status_126_is_not_misreported_as_authorization_denial(self):
        with patch('system_info.protected.trusted_tool', side_effect=['/usr/bin/pkexec','/usr/sbin/smartctl']), \
             patch('system_info.protected.subprocess.run', return_value=SimpleNamespace(returncode=126,stdout=b'{"smart_status":{"passed":false}}')):
            self.assertFalse(read_protected('smart','/dev/sda')['smart_status']['passed'])

    def test_short_trailing_firmware_header_is_rejected(self):
        from test_hardware import smbios_fixture
        # Remove the complete end marker, then append a partial next header.
        blob = smbios_fixture()[:-6] + b'\x01'
        with self.assertRaises(ValueError): parse_smbios(blob)

    def test_x11_negative_monitor_offsets_are_supported(self):
        with patch.dict(os.environ, {'XDG_SESSION_TYPE':'x11'}), \
             patch('system_info.collectors.gpu.run_cmd', return_value='HDMI-1 connected 1920x1080-1920+0\n'):
            self.assertEqual(x11_modes()['HDMI-1'], '1920x1080')


class CliTests(unittest.TestCase):
    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('system_info.main.SystemInfoApp') as factory:
            factory.return_value.category_names = ['overview','system']
            factory.return_value.collect_all.return_value = example_snapshot()
            factory.return_value.collect.return_value = example_snapshot()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = cli_main(args)
            return result, stdout.getvalue(), stderr.getvalue(), factory.return_value

    def test_cli_private_json_is_default(self):
        result, text, _, _ = self.invoke(['--json'])
        self.assertEqual(result, 0)
        self.assertNotIn('DEMO-SERIAL-PRIVATE', text)
        self.assertTrue(json.loads(text)['privacy']['identifiers_hidden'])

    def test_cli_include_identifiers_is_explicit(self):
        _, text, _, _ = self.invoke(['--json','--include-identifiers'])
        self.assertIn('DEMO-SERIAL-PRIVATE', text)

    def test_cli_selected_overview_honors_sequential(self):
        _, _, _, app = self.invoke(['overview','--sequential'])
        self.assertFalse(app.collect.call_args.kwargs['parallel'])

    def test_cli_file_output_does_not_also_print_identifiers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            result, stdout, _, _ = self.invoke(['--json','--output',str(path)])
            self.assertEqual(result, 0); self.assertEqual(stdout, '')
            self.assertEqual(json.loads(path.read_text())['app_version'], '1.4.0')

    def test_cli_bad_output_path_is_a_readable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            result, _, stderr, _ = self.invoke(['--output',str(Path(folder)/'missing/report.txt')])
            self.assertEqual(result, 2)
            self.assertIn('error:', stderr)
