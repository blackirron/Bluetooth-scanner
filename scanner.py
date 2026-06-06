"""Bluetooth device scanner supporting BLE and Classic Bluetooth."""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import dbus
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


@dataclass
class BluetoothDevice:
    address: str
    name: str
    device_type: str  # "ble" | "classic" | "paired"
    rssi: int | None = None
    connectable: bool = True
    manufacturer: str | None = None
    services: list[str] = field(default_factory=list)
    uuids: list[str] = field(default_factory=list)
    last_seen: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Common BLE manufacturer IDs (Arduino, Espressif, Nordic, etc.)
MANUFACTURER_NAMES: dict[int, str] = {
    0x004C: "Apple",
    0x0006: "Microsoft",
    0x00E0: "Google",
    0x0059: "Nordic Semiconductor",
    0x02E5: "Espressif (ESP32)",
    0x0A5C: "Broadcom",
    0x0075: "Samsung",
    0x0087: "Garmin",
    0x0499: "Ruuvi Innovations",
    0xFFFF: "Development Board",
}

# Keywords that hint at maker/hobbyist boards
MAKER_KEYWORDS = (
    "arduino", "esp32", "esp8266", "nordic", "nrf", "hc-05", "hc-06",
    "raspberry", "pi", "ble", "nano", "feather", "particle", "teensy",
    "stm32", "micro:bit", "bbc", "adafruit", "sparkfun", "lolin",
    "wemos", "ttgo", "heltec", "m5stack", "blueduino", "hm-10",
    "jdy", "rfduino", "bluno", "linkit", "edison", "zigbee",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_manufacturer(manufacturer_data: dict[int, bytes] | None) -> str | None:
    if not manufacturer_data:
        return None
    for company_id, _ in manufacturer_data.items():
        if company_id in MANUFACTURER_NAMES:
            return MANUFACTURER_NAMES[company_id]
    ids = ", ".join(f"0x{k:04X}" for k in manufacturer_data)
    return f"Unknown ({ids})"


def _is_maker_device(name: str, manufacturer: str | None) -> bool:
    haystack = f"{name} {manufacturer or ''}".lower()
    return any(kw in haystack for kw in MAKER_KEYWORDS)


def _ble_device_to_model(
    device: BLEDevice, adv: AdvertisementData | None
) -> BluetoothDevice:
    name = device.name or (adv.local_name if adv else None) or "Unknown"
    manufacturer = _parse_manufacturer(adv.manufacturer_data if adv else None)
    uuids: list[str] = []
    services: list[str] = []

    if adv:
        uuids = list(adv.service_uuids) if adv.service_uuids else []
        if adv.service_data:
            services = list(adv.service_data.keys())

    return BluetoothDevice(
        address=device.address,
        name=name,
        device_type="ble",
        rssi=adv.rssi if adv else None,
        connectable=True,
        manufacturer=manufacturer,
        services=services,
        uuids=uuids,
        last_seen=_now_iso(),
        extra={
            "is_maker_board": _is_maker_device(name, manufacturer),
            "tx_power": adv.tx_power if adv else None,
        },
    )


class BluetoothScanner:
    def __init__(self) -> None:
        self._devices: dict[str, BluetoothDevice] = {}
        self._scanning = False
        self._lock = asyncio.Lock()

    @property
    def devices(self) -> list[BluetoothDevice]:
        return sorted(
            self._devices.values(),
            key=lambda d: (d.rssi is None, -(d.rssi or -999), d.name),
        )

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    def get_devices_dict(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self.devices]

    def _upsert(self, device: BluetoothDevice) -> None:
        key = device.address.upper()
        if key in self._devices:
            existing = self._devices[key]
            if device.name != "Unknown":
                existing.name = device.name
            if device.rssi is not None:
                existing.rssi = device.rssi
            existing.last_seen = device.last_seen
            if device.manufacturer:
                existing.manufacturer = device.manufacturer
            if device.uuids:
                existing.uuids = list(set(existing.uuids + device.uuids))
            if device.services:
                existing.services = list(set(existing.services + device.services))
            existing.extra.update(device.extra)
        else:
            self._devices[key] = device

    async def scan_ble(self, duration: float = 8.0) -> None:
        discovered: dict[str, tuple[BLEDevice, AdvertisementData | None]] = {}

        def detection_callback(
            device: BLEDevice, adv: AdvertisementData
        ) -> None:
            discovered[device.address] = (device, adv)

        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        await asyncio.sleep(duration)
        await scanner.stop()

        for device, adv in discovered.values():
            self._upsert(_ble_device_to_model(device, adv))

    def scan_classic_bluetoothctl(self, timeout: int = 10) -> None:
        """Discover classic Bluetooth devices via bluetoothctl."""
        try:
            proc = subprocess.run(
                ["bluetoothctl", "--timeout", str(timeout), "scan", "on"],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            output = proc.stdout + proc.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return

        pattern = re.compile(
            r"Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", re.MULTILINE
        )
        for match in pattern.finditer(output):
            address, name = match.group(1), match.group(2).strip()
            self._upsert(
                BluetoothDevice(
                    address=address,
                    name=name,
                    device_type="classic",
                    connectable=True,
                    last_seen=_now_iso(),
                    extra={"is_maker_board": _is_maker_device(name, None)},
                )
            )

    def scan_paired_devices(self) -> None:
        """List already-paired devices from BlueZ."""
        try:
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager",
            )
            objects = manager.GetManagedObjects()
        except dbus.exceptions.DBusException:
            return

        for path, interfaces in objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            props = interfaces["org.bluez.Device1"]
            address = str(props.get("Address", ""))
            if not address:
                continue
            name = str(props.get("Name", props.get("Alias", "Unknown")))
            paired = bool(props.get("Paired", False))
            connected = bool(props.get("Connected", False))
            rssi = int(props["RSSI"]) if "RSSI" in props else None
            uuids = [str(u) for u in props.get("UUIDs", [])]

            self._upsert(
                BluetoothDevice(
                    address=address,
                    name=name,
                    device_type="paired" if paired else "classic",
                    rssi=rssi,
                    connectable=bool(props.get("LegacyPairing", True)),
                    uuids=uuids,
                    last_seen=_now_iso(),
                    extra={
                        "paired": paired,
                        "connected": connected,
                        "is_maker_board": _is_maker_device(name, None),
                        "icon": str(props.get("Icon", "")),
                    },
                )
            )

    def scan_adapter_info(self) -> dict[str, Any]:
        """Return local adapter status."""
        info: dict[str, Any] = {"adapters": []}
        try:
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager",
            )
            objects = manager.GetManagedObjects()
        except dbus.exceptions.DBusException as e:
            info["error"] = str(e)
            return info

        for path, interfaces in objects.items():
            if "org.bluez.Adapter1" not in interfaces:
                continue
            props = interfaces["org.bluez.Adapter1"]
            info["adapters"].append({
                "path": str(path),
                "address": str(props.get("Address", "")),
                "name": str(props.get("Name", "")),
                "alias": str(props.get("Alias", "")),
                "powered": bool(props.get("Powered", False)),
                "discoverable": bool(props.get("Discoverable", False)),
                "pairable": bool(props.get("Pairable", False)),
                "discovering": bool(props.get("Discovering", False)),
            })
        return info

    async def full_scan(self, ble_duration: float = 8.0) -> list[dict[str, Any]]:
        async with self._lock:
            if self._scanning:
                return self.get_devices_dict()
            self._scanning = True
            try:
                loop = asyncio.get_event_loop()
                self.scan_paired_devices()
                await asyncio.gather(
                    self.scan_ble(ble_duration),
                    loop.run_in_executor(
                        None, self.scan_classic_bluetoothctl, 10
                    ),
                )
                return self.get_devices_dict()
            finally:
                self._scanning = False

    def clear(self) -> None:
        self._devices.clear()
