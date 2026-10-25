"""One bounded external scripting worker, writing protocol data to a private file."""
import json
from pathlib import Path
import sys
import time
from native import connect, discover, failure, select
from operations import dispatch, invoke, MUTATIONS


def run(request):
    mutation = request.get("operation") in MUTATIONS and request.get("arguments", {}).get("confirmed") is True
    try:
        def check():
            if time.time() >= request["expires_at"]:
                raise ValueError("Request expired; do not retry a mutation automatically")
            return select(discover(), request["session_id"])
        selected = check()
        resolve = connect(selected)
        check()
        version = invoke(resolve, "GetVersion")
        if not isinstance(version, (list, tuple)) or not version or int(version[0]) < 21:
            raise ValueError("This release targets Resolve Studio 21 or later; installed API is older or version cannot be verified")
        data = dispatch(resolve, request, check)
        return {"ok": True, "data": data}
    except BaseException as exc:
        return failure("operation_failed", str(exc), execution_uncertain=mutation,
                       note="Earlier changes may exist after a failed write. Inspect state before retrying; never retry automatically." if mutation else "No mutation was requested.")


if __name__ == "__main__":
    response = run(json.loads(sys.stdin.read(262145)))
    try:
        encoded = json.dumps(response, ensure_ascii=True, allow_nan=False)
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            encoded = json.dumps(failure("response_too_large", "Result exceeded 2 MiB. A requested write may have completed; inspect state before retrying."))
    except (TypeError, ValueError):
        encoded = json.dumps(failure("invalid_sdk_result", "SDK returned non-JSON data. A requested write may have completed; inspect state before retrying."))
    Path(sys.argv[1]).write_text(encoded, encoding="utf-8")
