"""Stream actual screening and TradingAgents events to the local dashboard."""

import asyncio
from datetime import datetime, timezone
import json
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from routers.groq_analysis import require_local_client
from schemas.signal_scanner import SignalScannerRequest
from services.signal_scanner import ScanCancelled, SignalScannerService

router = APIRouter(dependencies=[Depends(require_local_client)])
_scan_lock = threading.Lock()


def _scanner():
    return SignalScannerService()


@router.post("/analysis/scanner/stream")
async def stream_scanner(
    body: SignalScannerRequest, request: Request, service=Depends(_scanner)
):
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(
            409,
            detail={
                "code": "SCANNER_BUSY",
                "message": "Another scan is still running or stopping.",
            },
        )
    events = queue.Queue(maxsize=128)
    cancelled = threading.Event()

    def emit(kind, data):
        if cancelled.is_set():
            raise ScanCancelled()
        events.put_nowait(
            {"type": kind, "data": data, "at": datetime.now(timezone.utc).isoformat()}
        )

    def work():
        try:
            service.run(body, emit, cancelled)
        except ScanCancelled:
            pass
        except Exception:
            if not cancelled.is_set():
                emit(
                    "scan_error",
                    {
                        "code": "SCANNER_FAILED",
                        "message": "Fresh market data or the research service was unavailable. Try a new scan.",
                    },
                )
        finally:
            _scan_lock.release()
            events.put_nowait(None)

    threading.Thread(target=work, daemon=True, name="signal-scanner").start()

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.to_thread(events.get, True, 0.5)
                except queue.Empty:
                    yield json.dumps(
                        {
                            "type": "heartbeat",
                            "data": {},
                            "at": datetime.now(timezone.utc).isoformat(),
                        }
                    ) + "\n"
                    continue
                if item is None:
                    break
                yield json.dumps(item, allow_nan=False) + "\n"
        finally:
            cancelled.set()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )
