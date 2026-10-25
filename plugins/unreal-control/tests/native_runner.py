"""Own a hidden Unreal Editor process and a marked disposable project only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
EXE=Path(os.environ.get('BUBBLE_UNREAL_EXE','C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe'))
scratch=ROOT/'.test-runtime';scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='native-editor-',dir=scratch) as directory:
    project=Path(directory)
    (project/'BUBBLE_DISPOSABLE_FIXTURE').write_text('Owned fixture; no user assets')
    manifest=project/'Fixture.uproject'
    manifest.write_text(json.dumps({'FileVersion':3,'EngineAssociation':'5.5','Plugins':[{'Name':'PythonScriptPlugin','Enabled':True},{'Name':'EditorScriptingUtilities','Enabled':True}]}))
    target=str(ROOT/'tests/native_structured.py')
    runner=project/'run_editor.py'
    runner.write_text('import unreal,traceback\ntry:\n    exec(compile(open('+repr(target)+',encoding="utf-8").read(),'+repr(target)+',"exec"),dict(__file__='+repr(target)+'))\nexcept Exception:\n    traceback.print_exc()\nfinally:\n    unreal.SystemLibrary.quit_editor()\n',encoding='utf-8')
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    subprocess.run([str(EXE),str(manifest),'-unattended','-NoSplash','-NoSound','-NullRHI','-NoSourceControl','-NoLiveCoding','-ExecutePythonScript='+str(runner),'-abslog='+str(project/'editor.log')],stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,startupinfo=startup,timeout=240,check=True)
    result=project/'native-result.json'
    if not result.is_file():
        print((project/'editor.log').read_text(encoding='utf-8',errors='replace')[-18000:])
        raise AssertionError('Native test did not produce success evidence')
    print(result.read_text(encoding='utf-8'))
