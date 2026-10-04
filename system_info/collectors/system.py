"""Operating system / kernel / host meta collector."""

from __future__ import annotations

import os
import platform
import socket
import time

import psutil

from .base import Collector, read_file, run_cmd, which


def _os_release() -> dict[str, str]:
    out: dict[str, str] = {}
    raw = read_file("/etc/os-release")
    if not raw:
        return out
    for line in raw.splitlines():
        key, sep, val = line.partition("=")
        if sep:
            out[key.strip()] = val.strip().strip('"')
    return out


class SystemCollector(Collector):
    name = "system"
    title = "System / OS"

    def collect(self):
        r = self.new_result()

        rel = _os_release()
        r.add("Distribution", rel.get("PRETTY_NAME"))
        r.add("Distro ID", rel.get("ID"))
        r.add("Version", rel.get("VERSION"))
        r.add("Home URL", rel.get("HOME_URL"))

        r.add("Kernel", platform.release())
        r.add("Kernel version", platform.version())
        r.add("App Python runtime", platform.python_version(), advanced=True)
        r.add("Platform", platform.platform(), advanced=True)
        r.add("Machine", platform.machine())
        r.add("Libc", " ".join(platform.libc_ver()), advanced=True)

        boot = psutil.boot_time()
        r.add("Boot time", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot)))
        r.add("Uptime", self._format_uptime())

        r.add("Hostname (nodename)", platform.node())
        r.add("Username", os.environ.get("USER", "unknown"))
        r.add("UID / GID", f"{os.getuid()} / {os.getgid()}", advanced=True)
        r.add("Locale", ".".join(str(x) for x in locale_pair()))
        r.add("Timezone", self._timezone())
        r.add("Virtualization", self._container())
        r.add("Desktop environment", os.environ.get("XDG_CURRENT_DESKTOP") or "Not reported")
        r.add("Desktop session", os.environ.get("XDG_SESSION_TYPE") or "Not reported")

        # Logged-in users via psutil.
        for u in psutil.users():
            r.add_record({
                "kind": "user",
                "name": u.name,
                "terminal": u.terminal,
                "host": u.host,
                "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(u.started)),
            })
        return r

    @staticmethod
    def _format_uptime() -> str:
        raw = read_file("/proc/uptime")
        if not raw:
            return "unavailable"
        secs = float(raw.split()[0])
        days, rem = divmod(int(secs), 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs_r = divmod(rem, 60)
        return f"{days}d {hours}h {mins}m {secs_r}s"

    @staticmethod
    def _timezone() -> str:
        from datetime import datetime
        return datetime.now().astimezone().strftime("%Z UTC%z")

    @staticmethod
    def _container() -> str:
        # Cheap container detection.
        try:
            cgroup = read_file("/proc/1/cgroup") or ""
            if "docker" in cgroup or "containerd" in cgroup:
                return "container (cgroup)"
        except Exception:
            pass
        if os.path.exists("/.dockerenv"):
            return "docker"
        if which("systemd-detect-virt"):
            import subprocess
            try:
                proc=subprocess.run(["systemd-detect-virt"],capture_output=True,text=True,timeout=3)
                if proc.returncode==0:return proc.stdout.strip()
                if proc.returncode==1:return "No virtualization detected"
            except (OSError,subprocess.TimeoutExpired):pass
        return "Not reported"


def locale_pair() -> tuple[str, str]:
    import locale
    try:
        return locale.getlocale()
    except Exception:
        return ("unknown", "unknown")
