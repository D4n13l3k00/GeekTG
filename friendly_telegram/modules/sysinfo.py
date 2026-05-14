"""System information dashboard — neofetch/fastfetch in an inline form.

Renders a card with host / CPU / RAM / disk / network / process stats and
swaps sections via inline buttons. Heavy probing is offloaded to a thread
with ``utils.run_sync`` so the userbot's event loop never stalls, even
when ``psutil`` does a syscall-heavy sweep.

``psutil`` is a soft dependency (Termux can't build it) — when it's
missing we fall back to ``/proc`` reads and ``shutil.disk_usage`` so the
command still produces a useful card.
"""

# scope: inline

import logging
import os
import platform
import shutil
import socket
import time
from typing import Any, Callable, Dict, List, Optional

from telethon.tl.custom import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


_SECTION_OVERVIEW = "overview"
_SECTION_CPU = "cpu"
_SECTION_MEMORY = "memory"
_SECTION_DISK = "disk"
_SECTION_NETWORK = "network"
_SECTION_PROCESS = "process"

_SECTIONS = (
    _SECTION_OVERVIEW,
    _SECTION_CPU,
    _SECTION_MEMORY,
    _SECTION_DISK,
    _SECTION_NETWORK,
    _SECTION_PROCESS,
)

_BAR_WIDTH = 14
_BAR_FILL = "█"
_BAR_EMPTY = "░"


def _try_psutil():
    try:
        import psutil  # noqa: WPS433
    except Exception:
        return None
    return psutil


def _human_bytes(n: float) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024.0:
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024.0
    return f"{n:,.1f} EiB"


def _human_seconds(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    if minutes or hours or days:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)


def _bar(percent: float, width: int = _BAR_WIDTH) -> str:
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round(pct / 100.0 * width))
    return _BAR_FILL * filled + _BAR_EMPTY * (width - filled)


def _read_first_line(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readline().strip()
    except OSError:
        return None


def _proc_meminfo() -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for raw in fh:
                key, _, rest = raw.partition(":")
                if not rest:
                    continue
                value = rest.strip().split()
                if not value:
                    continue
                try:
                    out[key.strip()] = int(value[0]) * 1024  # kB → bytes
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
            for raw in fh:
                if raw.startswith("model name"):
                    _, _, name = raw.partition(":")
                    return name.strip()
    except OSError:
        pass
    return platform.processor() or "Unknown"


def _distro_name() -> str:
    line = _read_first_line("/etc/os-release")
    if line and line.startswith("PRETTY_NAME"):
        try:
            return line.split("=", 1)[1].strip().strip('"')
        except (IndexError, ValueError):
            pass
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for raw in fh:
                if raw.startswith("PRETTY_NAME="):
                    return raw.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}".strip()


def _hostname() -> str:
    try:
        return socket.gethostname() or "localhost"
    except OSError:
        return "localhost"


def _read_proc_stat() -> Dict[str, tuple]:
    """Parse ``/proc/stat`` into ``{'cpu': (...), 'cpu0': (...), ...}``."""
    out: Dict[str, tuple] = {}
    try:
        with open("/proc/stat", "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.startswith("cpu"):
                    break
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    out[parts[0]] = tuple(int(x) for x in parts[1:])
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _cpu_pct(t1: Optional[tuple], t2: Optional[tuple]) -> Optional[float]:
    """Convert two ``/proc/stat`` cpu rows into a busy-% delta."""
    if not t1 or not t2:
        return None
    idle1 = t1[3] + (t1[4] if len(t1) > 4 else 0)
    idle2 = t2[3] + (t2[4] if len(t2) > 4 else 0)
    total1 = sum(t1)
    total2 = sum(t2)
    dt = total2 - total1
    di = idle2 - idle1
    if dt <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1.0 - di / dt) * 100.0)), 1)


def _read_pid_stat(pid: int) -> Optional[tuple]:
    """Return ``(utime, stime, starttime)`` (clock ticks) from ``/proc/<pid>/stat``.

    The ``comm`` field can contain spaces and even closing-parens, so we
    split from the **last** ``)`` to keep field offsets stable.
    """
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as fh:
            data = fh.read()
    except OSError:
        return None
    rp = data.rfind(")")
    if rp < 0:
        return None
    rest = data[rp + 2 :].split()
    # man 5 proc: utime=14, stime=15, starttime=22 (1-indexed; pid+comm
    # consumed → subtract 3 to index into ``rest``).
    try:
        return (int(rest[11]), int(rest[12]), int(rest[19]))
    except (IndexError, ValueError):
        return None


def _proc_cpuinfo_freq_mhz() -> Optional[float]:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
            for raw in fh:
                if raw.startswith("cpu MHz"):
                    _, _, val = raw.partition(":")
                    try:
                        return float(val.strip())
                    except ValueError:
                        pass
    except OSError:
        pass
    return None


def _proc_net_dev() -> Dict[str, Dict[str, int]]:
    """Parse ``/proc/net/dev`` into ``{iface: {bytes_recv, ...}}``."""
    out: Dict[str, Dict[str, int]] = {}
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return out
    for raw in lines[2:]:  # skip the two header rows
        name, sep, rest = raw.partition(":")
        if not sep:
            continue
        parts = rest.split()
        if len(parts) < 16:
            continue
        try:
            out[name.strip()] = {
                "bytes_recv": int(parts[0]),
                "packets_recv": int(parts[1]),
                "bytes_sent": int(parts[8]),
                "packets_sent": int(parts[9]),
            }
        except ValueError:
            continue
    return out


def _iface_ipv4(name: str) -> Optional[str]:
    """``ioctl(SIOCGIFADDR)`` — Linux-only, silently skips elsewhere."""
    try:
        import fcntl  # noqa: WPS433
        import struct  # noqa: WPS433
    except ImportError:
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            packed = struct.pack("256s", name.encode("utf-8")[:15])
            res = fcntl.ioctl(s.fileno(), 0x8915, packed)  # SIOCGIFADDR
            return socket.inet_ntoa(res[20:24])
    except OSError:
        return None


def _collect_snapshot(data_dir: str) -> Dict[str, Any]:
    """Run all blocking probes in one shot — call via ``run_sync``."""
    psutil = _try_psutil()
    snap: Dict[str, Any] = {
        "available": psutil is not None,
        "host": {
            "hostname": _hostname(),
            "distro": _distro_name(),
            "kernel": f"{platform.system()} {platform.release()}",
            "arch": platform.machine() or "unknown",
            "python": platform.python_version(),
        },
        "cpu": {"model": _cpu_model()},
        "memory": {},
        "swap": {},
        "disk": {},
        "net": {},
        "proc": {},
    }

    boot = None
    if psutil is not None:
        try:
            boot = psutil.boot_time()
        except Exception:
            logger.debug("psutil.boot_time failed", exc_info=True)
    if boot is None:
        uptime_line = _read_first_line("/proc/uptime")
        if uptime_line:
            try:
                boot = time.time() - float(uptime_line.split()[0])
            except (ValueError, IndexError):
                boot = None
    snap["host"]["boot_time"] = boot
    snap["host"]["uptime"] = (time.time() - boot) if boot else None

    cpu = snap["cpu"]
    if psutil is not None:
        try:
            cpu["physical"] = psutil.cpu_count(logical=False)
            cpu["logical"] = psutil.cpu_count(logical=True)
        except Exception:
            cpu["physical"] = None
            cpu["logical"] = os.cpu_count()
        try:
            freq = psutil.cpu_freq()
            cpu["freq_mhz"] = round(freq.current, 0) if freq else None
            cpu["freq_max_mhz"] = round(freq.max, 0) if freq and freq.max else None
        except Exception:
            cpu["freq_mhz"] = None
            cpu["freq_max_mhz"] = None
        try:
            cpu["percent_total"] = psutil.cpu_percent(interval=0.25)
            cpu["percent_per_core"] = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            cpu["percent_total"] = None
            cpu["percent_per_core"] = []
        try:
            la = psutil.getloadavg()
            cpu["loadavg"] = (round(la[0], 2), round(la[1], 2), round(la[2], 2))
        except Exception:
            cpu["loadavg"] = None
    else:
        cpu["physical"] = None
        cpu["logical"] = os.cpu_count()
        try:
            la = os.getloadavg()
            cpu["loadavg"] = (round(la[0], 2), round(la[1], 2), round(la[2], 2))
        except OSError:
            cpu["loadavg"] = None
        cpu["freq_mhz"] = _proc_cpuinfo_freq_mhz()
        cpu["freq_max_mhz"] = None

        # CPU% via two /proc/stat samples, 150 ms apart. Total + per-core
        # in one shot — same call into _read_proc_stat twice.
        s1 = _read_proc_stat()
        proc_pid = os.getpid()
        pid_s1 = _read_pid_stat(proc_pid)
        time.sleep(0.15)
        s2 = _read_proc_stat()
        pid_s2 = _read_pid_stat(proc_pid)

        cpu["percent_total"] = _cpu_pct(s1.get("cpu"), s2.get("cpu"))
        per: List[float] = []
        for key in sorted(s2.keys()):
            if key == "cpu":
                continue
            value = _cpu_pct(s1.get(key), s2.get(key))
            if value is not None:
                per.append(value)
        cpu["percent_per_core"] = per
        snap["_pid_samples"] = (pid_s1, pid_s2)

    mem = snap["memory"]
    sw = snap["swap"]
    if psutil is not None:
        try:
            v = psutil.virtual_memory()
            mem.update(
                {
                    "total": v.total,
                    "available": v.available,
                    "used": v.used,
                    "percent": v.percent,
                }
            )
        except Exception:
            logger.debug("psutil.virtual_memory failed", exc_info=True)
        try:
            s = psutil.swap_memory()
            sw.update(
                {
                    "total": s.total,
                    "used": s.used,
                    "percent": s.percent,
                }
            )
        except Exception:
            logger.debug("psutil.swap_memory failed", exc_info=True)
    if not mem:
        info = _proc_meminfo()
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable") or info.get("MemFree", 0)
        used = max(0, total - available)
        percent = round(used / total * 100, 1) if total else 0.0
        mem.update(
            {
                "total": total,
                "available": available,
                "used": used,
                "percent": percent,
            }
        )
        sw_total = info.get("SwapTotal", 0)
        sw_free = info.get("SwapFree", 0)
        sw_used = max(0, sw_total - sw_free)
        sw_percent = round(sw_used / sw_total * 100, 1) if sw_total else 0.0
        sw.update({"total": sw_total, "used": sw_used, "percent": sw_percent})

    try:
        u = shutil.disk_usage(data_dir or "/")
        snap["disk"].update(
            {
                "path": data_dir or "/",
                "total": u.total,
                "used": u.used,
                "free": u.free,
                "percent": round(u.used / u.total * 100, 1) if u.total else 0.0,
            }
        )
    except OSError:
        logger.debug("disk_usage failed", exc_info=True)

    if psutil is not None:
        try:
            io = psutil.net_io_counters()
            snap["net"]["bytes_sent"] = io.bytes_sent
            snap["net"]["bytes_recv"] = io.bytes_recv
            snap["net"]["packets_sent"] = io.packets_sent
            snap["net"]["packets_recv"] = io.packets_recv
        except Exception:
            logger.debug("psutil.net_io_counters failed", exc_info=True)
        try:
            ifs = psutil.net_if_addrs()
            iface_summary = []
            for name, addrs in ifs.items():
                if name == "lo":
                    continue
                ipv4 = next(
                    (a.address for a in addrs if a.family == socket.AF_INET),
                    None,
                )
                if ipv4:
                    iface_summary.append((name, ipv4))
            snap["net"]["ifaces"] = iface_summary[:6]
        except Exception:
            snap["net"]["ifaces"] = []
    else:
        ifaces = _proc_net_dev()
        if ifaces:
            totals = {
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0,
            }
            for name, stats in ifaces.items():
                if name == "lo":
                    continue
                for key, value in stats.items():
                    totals[key] += value
            snap["net"].update(totals)
            iface_summary = []
            for name in ifaces:
                if name == "lo":
                    continue
                ip = _iface_ipv4(name)
                if ip:
                    iface_summary.append((name, ip))
            snap["net"]["ifaces"] = iface_summary[:6]
        else:
            snap["net"]["ifaces"] = []

    if psutil is not None:
        try:
            proc = psutil.Process(os.getpid())
            with proc.oneshot():
                ct = proc.create_time()
                snap["proc"].update(
                    {
                        "pid": proc.pid,
                        "rss": proc.memory_info().rss,
                        "vms": proc.memory_info().vms,
                        "threads": proc.num_threads(),
                        "cpu_percent": round(proc.cpu_percent(interval=None), 1),
                        "uptime": time.time() - ct,
                    }
                )
                try:
                    snap["proc"]["fds"] = proc.num_fds()
                except Exception:
                    snap["proc"]["fds"] = None
        except Exception:
            logger.debug("psutil.Process probe failed", exc_info=True)
    if not snap["proc"]:
        pid = os.getpid()
        proc_info: Dict[str, Any] = {"pid": pid}
        try:
            with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fh:
                for raw in fh:
                    if raw.startswith("VmRSS:"):
                        try:
                            proc_info["rss"] = int(raw.split()[1]) * 1024
                        except (IndexError, ValueError):
                            pass
                    elif raw.startswith("VmSize:"):
                        try:
                            proc_info["vms"] = int(raw.split()[1]) * 1024
                        except (IndexError, ValueError):
                            pass
                    elif raw.startswith("Threads:"):
                        try:
                            proc_info["threads"] = int(raw.split()[1])
                        except (IndexError, ValueError):
                            pass
        except OSError:
            pass

        try:
            proc_info["fds"] = len(os.listdir(f"/proc/{pid}/fd"))
        except OSError:
            proc_info["fds"] = None

        # Uptime + CPU% via /proc/<pid>/stat. starttime is in clock ticks
        # since boot; subtract from now-vs-boot.
        pid_samples = snap.pop("_pid_samples", (None, None))
        pid_s1, pid_s2 = pid_samples
        if pid_s2 is None:
            pid_s2 = _read_pid_stat(pid)
        if pid_s2 is not None:
            try:
                ticks = os.sysconf("SC_CLK_TCK") or 100
            except (ValueError, OSError):
                ticks = 100
            if boot:
                proc_uptime = max(0.0, time.time() - boot - pid_s2[2] / ticks)
                proc_info["uptime"] = proc_uptime
            if pid_s1 is not None:
                used = (pid_s2[0] + pid_s2[1]) - (pid_s1[0] + pid_s1[1])
                # 0.15s sample interval — same one used for /proc/stat above.
                proc_cpu = (used / ticks) / 0.15 * 100.0
                proc_info["cpu_percent"] = round(max(0.0, proc_cpu), 1)

        proc_info.setdefault("rss", None)
        proc_info.setdefault("vms", None)
        proc_info.setdefault("threads", None)
        proc_info.setdefault("uptime", None)
        proc_info.setdefault("cpu_percent", None)
        snap["proc"] = proc_info
    snap.pop("_pid_samples", None)

    return snap


# ---------------------------------------------------------------- rendering


def _render_overview(snap: Dict[str, Any]) -> str:
    h = snap["host"]
    cpu = snap["cpu"]
    mem = snap["memory"]
    disk = snap["disk"]
    proc = snap["proc"]

    cpu_pct = cpu.get("percent_total")
    cpu_line = (
        f"{_bar(cpu_pct)}  <code>{cpu_pct:.1f}%</code>"
        if cpu_pct is not None
        else "<code>—</code>"
    )
    mem_pct = mem.get("percent", 0.0) or 0.0
    mem_line = (
        f"{_bar(mem_pct)}  <code>{mem_pct:.1f}%</code>"
        f"  <code>{_human_bytes(mem.get('used'))}/{_human_bytes(mem.get('total'))}</code>"
        if mem
        else "<code>—</code>"
    )
    disk_pct = disk.get("percent", 0.0) or 0.0
    disk_line = (
        f"{_bar(disk_pct)}  <code>{disk_pct:.1f}%</code>"
        f"  <code>{_human_bytes(disk.get('used'))}/{_human_bytes(disk.get('total'))}</code>"
        if disk
        else "<code>—</code>"
    )

    lines = [
        "<tg-emoji emoji-id='5282843764451195532'>🖥</tg-emoji> <b>System overview</b>",
        f"🏷 <b>Host:</b> <code>{utils.escape_html(h['hostname'])}</code>",
        f"<tg-emoji emoji-id='5361541227604878624'>🐧</tg-emoji> <b>OS:</b> <code>{utils.escape_html(h['distro'])}</code>",
        (
            f"<tg-emoji emoji-id='5217444336089714383'>🧬</tg-emoji> <b>Kernel:</b> <code>{utils.escape_html(h['kernel'])}</code> "
            f"(<code>{utils.escape_html(h['arch'])}</code>)"
        ),
        f"<tg-emoji emoji-id='5409076727341130651'>🐍</tg-emoji> <b>Python:</b> <code>{utils.escape_html(h['python'])}</code>",
    ]
    if h.get("uptime"):
        lines.append(f"⏱ <b>Uptime:</b> <code>{_human_seconds(h['uptime'])}</code>")
    if proc.get("uptime"):
        lines.append(
            f"<tg-emoji emoji-id='5372981976804366741'>🤖</tg-emoji> <b>Bot uptime:</b> <code>{_human_seconds(proc['uptime'])}</code>"
        )
    lines.append("")
    lines.append(
        f"<tg-emoji emoji-id='5431449001532594346'>⚡</tg-emoji> <b>CPU:</b> {cpu_line}"
    )
    lines.append(f"💾 <b>RAM:</b> {mem_line}")
    lines.append(f"📀 <b>Disk:</b> {disk_line}")
    return "\n".join(lines)


def _render_cpu(snap: Dict[str, Any]) -> str:
    cpu = snap["cpu"]
    lines = [
        "<tg-emoji emoji-id='5431449001532594346'>⚡</tg-emoji> <b>CPU</b>",
        f"<tg-emoji emoji-id='5237799019329105246'>🧠</tg-emoji> <b>Model:</b> <code>{utils.escape_html(cpu.get('model') or 'Unknown')}</code>",
    ]
    cores = []
    if cpu.get("physical"):
        cores.append(f"{cpu['physical']} physical")
    if cpu.get("logical"):
        cores.append(f"{cpu['logical']} logical")
    if cores:
        lines.append(f"🧩 <b>Cores:</b> <code>{' / '.join(cores)}</code>")
    if cpu.get("freq_mhz"):
        freq = f"{cpu['freq_mhz']:.0f} MHz"
        if cpu.get("freq_max_mhz"):
            freq += f" (max {cpu['freq_max_mhz']:.0f})"
        lines.append(
            f"<tg-emoji emoji-id='5373001317042101552'>📈</tg-emoji> <b>Frequency:</b> <code>{freq}</code>"
        )
    if cpu.get("loadavg"):
        la = cpu["loadavg"]
        lines.append(
            f"<tg-emoji emoji-id='5431577498364158238'>📊</tg-emoji> <b>Load avg:</b> <code>{la[0]} / {la[1]} / {la[2]}</code>"
        )
    pct = cpu.get("percent_total")
    if pct is not None:
        lines.append(
            f"<tg-emoji emoji-id='5420315771991497307'>🔥</tg-emoji> <b>Total:</b> {_bar(pct)} <code>{pct:.1f}%</code>"
        )
    per = cpu.get("percent_per_core") or []
    if per:
        lines.append("")
        lines.append("🔢 <b>Per-core:</b>")
        for idx, value in enumerate(per[:16]):
            lines.append(
                f"   <code>#{idx:>2}</code> {_bar(value, 10)} <code>{value:>5.1f}%</code>"
            )
        if len(per) > 16:
            lines.append(f"   <i>… and {len(per) - 16} more</i>")
    return "\n".join(lines)


def _render_memory(snap: Dict[str, Any]) -> str:
    mem = snap["memory"]
    swap = snap["swap"]
    lines = ["💾 <b>Memory</b>"]
    if mem:
        pct = mem.get("percent", 0.0) or 0.0
        lines.append(
            f"<tg-emoji emoji-id='5237799019329105246'>🧠</tg-emoji> <b>RAM:</b> {_bar(pct)} <code>{pct:.1f}%</code>"
        )
        lines.append(
            f"   <code>{_human_bytes(mem.get('used'))} / "
            f"{_human_bytes(mem.get('total'))}</code> "
            f"(free <code>{_human_bytes(mem.get('available'))}</code>)"
        )
    if swap and swap.get("total"):
        pct = swap.get("percent", 0.0) or 0.0
        lines.append("")
        lines.append(f"🔁 <b>Swap:</b> {_bar(pct)} <code>{pct:.1f}%</code>")
        lines.append(
            f"   <code>{_human_bytes(swap.get('used'))} / "
            f"{_human_bytes(swap.get('total'))}</code>"
        )
    elif swap:
        lines.append("")
        lines.append("🔁 <b>Swap:</b> <code>off</code>")
    return "\n".join(lines)


def _render_disk(snap: Dict[str, Any]) -> str:
    disk = snap["disk"]
    if not disk:
        return "📀 <b>Disk</b>\n<code>unavailable</code>"
    pct = disk.get("percent", 0.0) or 0.0
    return (
        "📀 <b>Disk</b>\n"
        f"<tg-emoji emoji-id='5431721976769027887'>📂</tg-emoji> <b>Path:</b> <code>{utils.escape_html(disk.get('path') or '/')}</code>\n"
        f"<tg-emoji emoji-id='5431577498364158238'>📊</tg-emoji> {_bar(pct)} <code>{pct:.1f}%</code>\n"
        f"📦 <b>Used:</b> <code>{_human_bytes(disk.get('used'))}</code>\n"
        f"<tg-emoji emoji-id='5364112491381006601'>🆓</tg-emoji> <b>Free:</b> <code>{_human_bytes(disk.get('free'))}</code>\n"
        f"🗄 <b>Total:</b> <code>{_human_bytes(disk.get('total'))}</code>"
    )


def _render_network(snap: Dict[str, Any]) -> str:
    net = snap["net"]
    lines = ["<tg-emoji emoji-id='5447410659077661506'>🌐</tg-emoji> <b>Network</b>"]
    if net.get("bytes_sent") is not None:
        lines.append(
            f"<tg-emoji emoji-id='5433614747381538714'>📤</tg-emoji> <b>Sent:</b> <code>{_human_bytes(net['bytes_sent'])}</code>"
            f"  ({net.get('packets_sent', 0):,} pkt)"
        )
        lines.append(
            f"<tg-emoji emoji-id='5433811242135331842'>📥</tg-emoji> <b>Recv:</b> <code>{_human_bytes(net['bytes_recv'])}</code>"
            f"  ({net.get('packets_recv', 0):,} pkt)"
        )
    else:
        lines.append("<code>counters unavailable</code>")
    ifaces = net.get("ifaces") or []
    if ifaces:
        lines.append("")
        lines.append(
            "<tg-emoji emoji-id='5321304062715517873'>🛰</tg-emoji> <b>Interfaces:</b>"
        )
        for name, ip in ifaces:
            lines.append(
                f"   <code>{utils.escape_html(name)}</code> → "
                f"<code>{utils.escape_html(ip)}</code>"
            )
    return "\n".join(lines)


def _render_process(snap: Dict[str, Any]) -> str:
    proc = snap["proc"]
    if not proc:
        return "<tg-emoji emoji-id='5372981976804366741'>🤖</tg-emoji> <b>Process</b>\n<code>unavailable</code>"
    lines = [
        "<tg-emoji emoji-id='5372981976804366741'>🤖</tg-emoji> <b>Process</b> (this userbot)"
    ]
    lines.append(
        f"<tg-emoji emoji-id='5818885490065017876'>🆔</tg-emoji> <b>PID:</b> <code>{proc.get('pid')}</code>"
    )
    if proc.get("uptime"):
        lines.append(f"⏱ <b>Uptime:</b> <code>{_human_seconds(proc['uptime'])}</code>")
    if proc.get("rss") is not None:
        lines.append(f"💾 <b>RSS:</b> <code>{_human_bytes(proc['rss'])}</code>")
    if proc.get("vms"):
        lines.append(f"📐 <b>VMS:</b> <code>{_human_bytes(proc['vms'])}</code>")
    if proc.get("threads") is not None:
        lines.append(f"🧵 <b>Threads:</b> <code>{proc['threads']}</code>")
    if proc.get("fds") is not None:
        lines.append(
            f"<tg-emoji emoji-id='5377844313575150051'>📎</tg-emoji> <b>FDs:</b> <code>{proc['fds']}</code>"
        )
    if proc.get("cpu_percent") is not None:
        lines.append(
            f"<tg-emoji emoji-id='5420315771991497307'>🔥</tg-emoji> <b>CPU:</b> {_bar(proc['cpu_percent'])} "
            f"<code>{proc['cpu_percent']:.1f}%</code>"
        )
    return "\n".join(lines)


_RENDERERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    _SECTION_OVERVIEW: _render_overview,
    _SECTION_CPU: _render_cpu,
    _SECTION_MEMORY: _render_memory,
    _SECTION_DISK: _render_disk,
    _SECTION_NETWORK: _render_network,
    _SECTION_PROCESS: _render_process,
}


# ---------------------------------------------------------------- module


@loader.tds
class SysInfoMod(loader.Module):
    """Fastfetch-style system stats with inline section switcher."""

    strings = {
        "name": "SysInfo",
        "footer": "\n\n🕓 <i>Updated: <code>{ts}</code></i>",
        "psutil_missing": (
            "\n\n⚠️ <i>psutil not installed — using /proc fallbacks.</i>"
        ),
        "title_overview": "🖥 Overview",
        "title_cpu": "⚡ CPU",
        "title_memory": "💾 RAM",
        "title_disk": "📀 Disk",
        "title_network": "🌐 Network",
        "title_process": "🤖 Process",
        "btn_refresh": "🔄 Refresh",
        "btn_close": "🚫 Close",
        "answer_refreshed": "🔄 Refreshed",
        "answer_closed": "🚫 Closed",
        "_disk_path_doc": (
            "Mount point inspected for disk stats. Empty = userbot data dir."
        ),
    }

    def __init__(self) -> None:
        self.config = loader.ModuleConfig(
            "DISK_PATH",
            "",
            lambda m: self.tr("_disk_path_doc", m),
        )

    # ------------------------------------------------------------ helpers

    def _data_dir(self) -> str:
        configured = (self.config["DISK_PATH"] or "").strip()
        if configured:
            return configured
        try:
            return utils.get_base_dir()
        except Exception:
            return os.getcwd()

    async def _snapshot(self) -> Dict[str, Any]:
        return await utils.run_sync(_collect_snapshot, self._data_dir())

    def _build_text(self, snap: Dict[str, Any], section: str) -> str:
        renderer = _RENDERERS.get(section, _render_overview)
        body = renderer(snap)
        body += self.tr("footer").format(
            ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        )
        if not snap.get("available"):
            body += self.tr("psutil_missing")
        return body

    def _build_markup(self, current: str) -> List[List[Dict[str, Any]]]:
        labels = {
            _SECTION_OVERVIEW: self.tr("title_overview"),
            _SECTION_CPU: self.tr("title_cpu"),
            _SECTION_MEMORY: self.tr("title_memory"),
            _SECTION_DISK: self.tr("title_disk"),
            _SECTION_NETWORK: self.tr("title_network"),
            _SECTION_PROCESS: self.tr("title_process"),
        }
        section_buttons = []
        for key in _SECTIONS:
            label = labels[key]
            if key == current:
                label = f"• {label} •"
            section_buttons.append(
                {
                    "text": label,
                    "callback": self._switch_section,
                    "args": (key,),
                }
            )
        rows: List[List[Dict[str, Any]]] = [
            section_buttons[:3],
            section_buttons[3:],
        ]
        rows.append(
            [
                {
                    "text": self.tr("btn_refresh"),
                    "callback": self._refresh,
                    "args": (current,),
                    "style": "primary",
                },
                {
                    "text": self.tr("btn_close"),
                    "callback": self._close,
                    "style": "danger",
                },
            ]
        )
        return rows

    # ------------------------------------------------------------ commands

    @loader.unrestricted
    async def sysinfocmd(self, message: Message) -> None:
        """Show system stats with inline buttons."""
        snap = await self._snapshot()
        await self.inline.form(
            text=self._build_text(snap, _SECTION_OVERVIEW),
            message=message,
            reply_markup=self._build_markup(_SECTION_OVERVIEW),
            ttl=600,
        )

    specscmd = sysinfocmd

    # ------------------------------------------------------------ callbacks

    async def _switch_section(self, call: InlineCall, section: str) -> None:
        snap = await self._snapshot()
        await call.edit(
            text=self._build_text(snap, section),
            reply_markup=self._build_markup(section),
        )

    async def _refresh(self, call: InlineCall, section: str) -> None:
        snap = await self._snapshot()
        await call.edit(
            text=self._build_text(snap, section),
            reply_markup=self._build_markup(section),
        )
        await call.answer(self.tr("answer_refreshed"))

    async def _close(self, call: InlineCall) -> None:
        await call.answer(self.tr("answer_closed"))
        await call.delete()
