"""Compile against installed Unity; optionally launch only a fresh batch fixture."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import installation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--editor", default="C:/Program Files/Unity/Hub/Editor/6000.1.0f1/Editor/Unity.exe")
    parser.add_argument("--run-editor", action="store_true")
    args = parser.parse_args()
    editor = Path(args.editor)
    data = editor.parent / "Data"
    scratch_root = ROOT / ".test-runtime"
    scratch_root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="unity-smoke-", dir=scratch_root))
    mono = data / "MonoBleedingEdge/bin/mono.exe"
    compiler = data / "MonoBleedingEdge/lib/mono/4.5/csc.exe"
    references = [data / "Managed/UnityEngine" / name for name in ("UnityEngine.CoreModule.dll", "UnityEngine.JSONSerializeModule.dll", "UnityEditor.CoreModule.dll")]
    references.append(data / "UnityReferenceAssemblies/unity-4.8-api/Facades/netstandard.dll")
    command = [str(mono), str(compiler), "/nologo", "/target:library", "/out:" + str(scratch / "Bubble.UnityControl.Editor.dll")]
    command += ["/reference:" + str(path) for path in references]
    command += [str(ROOT / "unity/Editor/BubbleUnityBridge.cs")]
    subprocess.run(command, check=True, timeout=60)
    print("PASS: C# compiled against installed Unity Editor assemblies")
    if not args.run_editor:
        return
    project = scratch / "Project"
    (project / "Assets/Editor").mkdir(parents=True)
    (project / "ProjectSettings").mkdir()
    (project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.1.0f1\n")
    (project / "Packages").mkdir()
    (project / "Packages/manifest.json").write_text('{"dependencies": {}}\n')
    result = installation.install_bridge(str(project), confirmed=True)
    if not result["ok"]:
        raise RuntimeError(result)
    shutil.copyfile(ROOT / "tests/UnitySmoke.cs", project / "Assets/Editor/UnitySmoke.cs")
    # Explicitly reference the Editor-only package from the smoke assembly.
    (project / "Assets/Editor/Bubble.Smoke.asmdef").write_text(json.dumps({"name": "Bubble.Smoke", "references": ["Bubble.UnityControl.Editor"], "includePlatforms": ["Editor"]}))
    log, report = scratch / "Editor.log", scratch / "result.txt"
    env = {**os.environ, "BUBBLE_UNITY_ALLOW_BATCH": "1", "BUBBLE_UNITY_SESSION_DIR": str(scratch / "sessions"), "BUBBLE_UNITY_SMOKE_RESULT": str(report)}
    print("Scratch fixture:", scratch, flush=True)
    try:
        process = subprocess.run([str(editor), "-batchmode", "-nographics", "-projectPath", str(project), "-executeMethod", "BubbleSmoke.Run", "-logFile", str(log)], env=env, timeout=240)
        if process.returncode or not report.exists() or not report.read_text(encoding="utf-8").startswith("PASS"):
            raise RuntimeError("Unity batch fixture failed; inspect " + str(log))
        print(report.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        raise RuntimeError("Unity batch fixture timed out; inspect license/compiler log " + str(log)) from None


if __name__ == "__main__":
    main()
