#!/usr/bin/env python3

import json
import re
import subprocess
from pathlib import Path

HWMON_PATH = Path("/sys/class/hwmon")

# Пороги по умолчанию, если hwmon их не отдаёт
DEFAULT_WARN = 70
DEFAULT_CRIT = 85
DISK_WARN = 45
DISK_CRIT = 55


def read_file(path):
    """Читает значение из файла Linux."""
    try:
        return path.read_text().strip()
    except (OSError, PermissionError):
        return None


def read_limit(device, number, kind):
    """Порог из hwmon (temp1_max / temp1_crit) в градусах или None."""
    raw = read_file(device / f"{number}_{kind}")
    try:
        value = int(raw) / 1000
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def get_chip_id(device):
    """
    Уникальное и стабильное имя чипа в стиле утилиты sensors:
    coretemp-isa-0000, nvme-pci-0100 и т.д.
    Не зависит от номера hwmonN.
    """
    name = read_file(device / "name") or "unknown"

    try:
        link = device / "device"
        real = link.resolve() if link.exists() else device.resolve().parent.parent
    except OSError:
        return name

    dev_name = real.name

    # PCI: 0000:00:1f.3
    m = re.fullmatch(r"[0-9a-f]{4}:([0-9a-f]{2}):([0-9a-f]{2})\.(\d)", dev_name)
    if m:
        bus, dev, fn = (int(x, 16) for x in m.groups())
        return f"{name}-pci-{(bus << 8) | (dev << 3) | fn:04x}"

    # platform: coretemp.0
    m = re.fullmatch(r".+\.(\d+)", dev_name)
    if m and real.parent.name == "platform":
        return f"{name}-isa-{int(m.group(1)):04x}"

    return f"{name}-{dev_name}"


def get_thresholds(device, number):
    """Возвращает (warn, crit) с проверкой на адекватность."""
    warn = read_limit(device, number, "max") or DEFAULT_WARN
    crit = read_limit(device, number, "crit") or DEFAULT_CRIT

    if crit <= warn:
        crit = warn + 10

    return round(warn, 1), round(crit, 1)


def get_temperatures():
    sensors = []

    for device in sorted(HWMON_PATH.glob("hwmon*")):
        chip = get_chip_id(device)
        seen = set()

        for temp_file in sorted(device.glob("temp*_input")):
            raw_value = read_file(temp_file)
            if raw_value is None:
                continue

            try:
                temperature = int(raw_value) / 1000
            except ValueError:
                continue

            number = temp_file.name.replace("_input", "")
            label = read_file(device / f"{number}_label") or number

            # Подпись должна быть уникальной внутри чипа
            if label in seen:
                label = f"{label} ({number})"
            seen.add(label)

            warn, crit = get_thresholds(device, number)

            sensors.append({
                "chip": chip,
                "sensor": label,
                "temperature": round(temperature, 2),
                "warn": warn,
                "crit": crit,
            })

    return sensors


def run_command(command):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15
        )
        return result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_physical_disks():
    output = run_command(["lsblk", "-dnpo", "NAME,TYPE"])
    disks = []

    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "disk":
            disks.append(parts[0])

    return disks


def get_disk_info(device):
    """Модель и серийный номер диска."""
    model = run_command(["lsblk", "-dno", "MODEL", device]).strip()
    serial = run_command(["lsblk", "-dno", "SERIAL", device]).strip()
    return model, serial


def get_disk_temperature(device):
    output = run_command(["smartctl", "-A", device])

    for line in output.splitlines():
        parts = line.split()

        # SATA: атрибуты 194 и 190, сырое значение в 10-м столбце
        if len(parts) >= 10 and parts[0] in ("194", "190") and \
                parts[1] in ("Temperature_Celsius", "Airflow_Temperature_Cel"):
            m = re.match(r"\d+", parts[9])
            if m:
                return int(m.group())

        # NVMe: "Temperature:   35 Celsius"
        m = re.match(r"^Temperature:\s+(\d+)\s+Celsius", line)
        if m:
            return int(m.group(1))

    return None


def collect_disks():
    result = []

    for device in get_physical_disks():
        temperature = get_disk_temperature(device)

        # Диски без данных пропускаем
        if temperature is None:
            continue

        model, serial = get_disk_info(device)

        result.append({
            "chip": "disk",
            "sensor": device,
            "model": model,
            "serial": serial,
            "temperature": temperature,
            "warn": DISK_WARN,
            "crit": DISK_CRIT,
        })

    return result


def main():
    data = {"sensors": get_temperatures() + collect_disks()}
    print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
