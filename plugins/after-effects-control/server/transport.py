"""One-shot native -r requests; no host installation, automatic retries or launch intent."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from native import select
from operations import script

_lock = threading.Lock()
_server_id = uuid.uuid4().hex
_tokens = {}
_handshake_tokens = {}


def failure(code, message):
    return {'ok': False, 'error': {'code': code, 'message': str(message)}}


def call(operation, session_id, expected_project_state=None, timeout=20, **args):
    if not 1 <= timeout <= 120:
        return failure('invalid_request', 'timeout must be 1–120 seconds')
    with _lock:
        try:
            selected = select(session_id)
            token = _tokens.get(session_id)
            if operation != 'project_info' and not token:
                raise ValueError('Read project info first to establish a native session token')
            # Reuse an attempted handshake token if AE accepted it but its reply
            # was lost. Only _tokens records a verified handshake for writes.
            token = token or _handshake_tokens.setdefault(session_id, uuid.uuid4().hex)
            with tempfile.TemporaryDirectory(prefix='bubble-ae-request-') as folder:
                request_id = uuid.uuid4().hex
                response = Path(folder) / 'response.json'
                request = dict(operation=operation, session_id=session_id, server_id=_server_id, token=token, request_id=request_id, expires_at=int((time.time()+timeout)*1000), response_path=str(response), expected_project_state=expected_project_state, args=args)
                path = Path(folder) / 'request.jsx'
                path.write_text(script(request), encoding='utf-8')
                if select(session_id) != selected:
                    raise ValueError('Session changed before dispatch')
                # Adobe forwards -r to its running application. A last-moment exit can
                # start a new process; token guards prevent mutations in that process.
                process = subprocess.Popen([selected['executable'], '-r', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                end = time.monotonic()+timeout
                while time.monotonic()<end:
                    if response.exists():
                        if response.stat().st_size>8*1024*1024:
                            return failure('response_too_large','Response exceeds 8 MiB. Operation may have completed; inspect state before any retry.')
                        try:
                            result=json.loads(response.read_text(encoding='utf-8-sig'))
                        except (json.JSONDecodeError, PermissionError):
                            time.sleep(.1)
                            continue
                        if select(session_id) != selected:
                            return failure('session_changed_outcome_unknown','Session changed during dispatch; inspect state before retrying.')
                        if result.get('request_id') != request_id:
                            raise ValueError('Response request token mismatch')
                        if operation=='project_info' and result.get('ok'):
                            _tokens[session_id]=token
                        result.pop('request_id',None)
                        return result
                    time.sleep(.1)
                return failure('timeout_outcome_unknown','No verified reply. Check After Effects scripting file/network preference and modal dialogs. Operation may have executed; never retry automatically. No preference was changed.')
        except Exception as exc:
            return failure('connection_error',exc)
