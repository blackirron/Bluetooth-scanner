# Bluetooth Scanner

A web app for discovering nearby Bluetooth devices — including **BLE** boards (Arduino Nano 33 BLE, ESP32, nRF52) and **Classic Bluetooth** modules (HC-05, HC-06).

## Features

- Scans **BLE** (Low Energy) and **Classic Bluetooth** simultaneously
- Shows paired and connected devices
- Highlights maker/hobbyist boards (Arduino, ESP32, Nordic, etc.)
- Live updates via WebSocket
- Filter by type, search by name/address
- Device detail modal with RSSI, services, manufacturer info

## Requirements

- Linux with BlueZ (`bluetoothd` running)
- Bluetooth adapter powered on
- Python 3.10+

## Setup

```bash
cd bluetooth-scanner
pip3 install --target ./vendor -r requirements.txt
```

> Requires system package `python3-dbus` for BlueZ integration:
> `sudo apt install python3-dbus python3-dbus.mainloop.glib`

## Run

```bash
./run.sh
```

Open **http://localhost:8765** in your browser and click **Scan Devices**.

> **Note:** BLE and classic scanning may require elevated permissions. If no devices appear, try:
> ```bash
> sudo setcap 'cap_net_raw,cap_net_admin+eip' .venv/bin/python3
> ```
> Or run with `sudo` (not recommended for daily use).

## Arduino / Maker Devices

| Device | Type | Typical name |
|--------|------|--------------|
| Arduino Nano 33 BLE | BLE | "Arduino" or custom name |
| ESP32 (BLE mode) | BLE | "ESP32" or custom |
| HC-05 / HC-06 | Classic | "HC-05", "linvor" |
| nRF52840 DK | BLE | "Nordic_UART" |
| BBC micro:bit | BLE | "BBC micro:bit" |

Use the **Maker boards** filter to show only hobbyist devices.
