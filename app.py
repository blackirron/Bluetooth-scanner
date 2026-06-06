"""Bluetooth Scanner web application."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scanner import BluetoothScanner

STATIC_DIR = Path(__file__).parent / "static"
scanner = BluetoothScanner()
active_websockets: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    active_websockets.clear()


app = FastAPI(title="Bluetooth Scanner", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status():
    return {
        "scanning": scanner.is_scanning,
        "device_count": len(scanner.devices),
        "adapter": scanner.scan_adapter_info(),
    }


@app.get("/api/devices")
async def get_devices():
    return {"devices": scanner.get_devices_dict(), "scanning": scanner.is_scanning}


@app.post("/api/scan")
async def start_scan():
    if scanner.is_scanning:
        return {"status": "already_scanning", "devices": scanner.get_devices_dict()}

    async def run_and_broadcast():
        devices = await scanner.full_scan()
        message = json.dumps({"type": "scan_complete", "devices": devices})
        dead: list[WebSocket] = []
        for ws in active_websockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            active_websockets.discard(ws)

    asyncio.create_task(run_and_broadcast())
    return {"status": "started"}


@app.post("/api/clear")
async def clear_devices():
    scanner.clear()
    return {"status": "cleared"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        await websocket.send_text(
            json.dumps({
                "type": "initial",
                "devices": scanner.get_devices_dict(),
                "scanning": scanner.is_scanning,
                "adapter": scanner.scan_adapter_info(),
            })
        )
        while True:
            data = await websocket.receive_text()
            if data == "scan":
                if not scanner.is_scanning:
                    devices = await scanner.full_scan()
                    await websocket.send_text(
                        json.dumps({"type": "scan_complete", "devices": devices})
                    )
            elif data == "status":
                await websocket.send_text(
                    json.dumps({
                        "type": "status",
                        "scanning": scanner.is_scanning,
                        "adapter": scanner.scan_adapter_info(),
                    })
                )
    except WebSocketDisconnect:
        pass
    finally:
        active_websockets.discard(websocket)
