"""Maintainer-only signed CEP release builder. No runtime installer/developer tool dependency."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signer", required=True, type=Path)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--password-env", default="BUBBLE_CEP_SIGNING_PASSWORD")
    parser.add_argument("--timestamp-url", help="Optional trusted timestamp service; otherwise certificate expiry applies")
    args = parser.parse_args()
    password = os.environ.get(args.password_env)
    if not password: parser.error("Signing password environment variable is empty")
    signer, certificate = args.signer.resolve(), args.certificate.resolve()
    if not signer.is_file() or not certificate.is_file(): parser.error("Signer and certificate must exist")
    with tempfile.TemporaryDirectory(prefix="bubble-cep-sign-") as temp:
        temp = Path(temp)
        candidate = temp / "premiere.zxp"
        command = [str(signer),"-sign",str(ROOT / "cep"),str(candidate),str(certificate),password]
        if args.timestamp_url: command += ["-tsa",args.timestamp_url]
        result = subprocess.run(command,cwd=temp,capture_output=True,text=True)
        if result.returncode: raise RuntimeError("Adobe signing failed: " + result.stdout + result.stderr)
        result = subprocess.run([str(signer),"-verify",str(candidate)],cwd=temp,capture_output=True,text=True)
        if result.returncode or "Signature verified successfully" not in result.stdout: raise RuntimeError("Adobe signature verification failed: " + result.stdout + result.stderr)
        extracted = temp / "signed"
        with zipfile.ZipFile(candidate) as archive:
            for name in archive.namelist():
                if ":" in name or name.startswith("/") or ".." in Path(name).parts or "\\" in name: raise ValueError("Unsafe ZIP entry")
            archive.extractall(extracted)
        sources = {x.relative_to(ROOT/"cep").as_posix():x.read_bytes() for x in (ROOT/"cep").rglob("*") if x.is_file()}
        payload = {x.relative_to(extracted).as_posix():x.read_bytes() for x in extracted.rglob("*") if x.is_file()}
        if set(payload) != set(sources) | {"META-INF/signatures.xml","mimetype"}: raise ValueError("Unexpected package file set")
        if any(payload[k] != v for k,v in sources.items()): raise ValueError("Signer modified source")
        dest = ROOT / "adobe/signed"
        for node in [dest,*dest.parents]:
            if node.exists() and (node.is_symlink() or getattr(node.stat(),"st_file_attributes",0)&0x400):
                raise ValueError("Refusing reparse-point build output")
        # Fixed build output only; no Adobe application folders are touched.
        if dest.exists():
            if dest.resolve() != ROOT.resolve()/"adobe/signed" or dest.is_symlink(): raise ValueError("Unsafe build output")
            existing = sorted(dest.rglob("*"),key=lambda x:len(x.parts),reverse=True)
            for file in existing:
                if (file.is_symlink() or getattr(file.stat(),"st_file_attributes",0)&0x400
                        or not file.resolve().is_relative_to(dest.resolve())):
                    raise ValueError("Unsafe build output link or escaped path")
            for file in existing:
                if file.is_file(): file.unlink()
                else: file.rmdir()
            dest.rmdir()
        shutil.copytree(extracted,dest)
        shutil.copy2(candidate,ROOT/"adobe/com.popostudio.bubble.premiere.zxp")
        release={"plugin_id":"com.popostudio.bubble.premiere","version":"0.2.0",
            "files":{k:hashlib.sha256(v).hexdigest() for k,v in sorted(payload.items())},
            "zxp_sha256":hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "signer":{"tool":"Adobe ZXPSignCmd","sha256":hashlib.sha256(signer.read_bytes()).hexdigest(),"timestamped":bool(args.timestamp_url)},
            "native_tested":False}
        (ROOT/"adobe/release.json").write_text(json.dumps(release,indent=2)+"\n",encoding="utf-8")
        print("Signed CEP release generated and verified. Native Premiere acceptance remains separate.")

if __name__ == "__main__": main()
