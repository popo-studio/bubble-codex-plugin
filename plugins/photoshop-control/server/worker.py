"""One request per isolated COM worker. Never launches Photoshop."""
import json
import os
import sys
import time
from native import discover, select, failure

SERIALIZER = r'''function encode(v) { if(v===null||v===undefined)return "null"; if(typeof v==="string")return '"'+v.replace(/[\\"\u0000-\u001f]/g,function(c){var n=c.charCodeAt(0).toString(16);return "\\u"+("0000"+n).slice(-4);})+'"';if(typeof v==="number")return isFinite(v)?String(v):"null";if(typeof v==="boolean")return String(v);var a=[],i;if(v instanceof Array){for(i=0;i<v.length;i++)a.push(encode(v[i]));return "["+a.join(",")+"]";}if(typeof v==="object"){for(i in v)if(v.hasOwnProperty(i))a.push(encode(i)+":"+encode(v[i]));return "{"+a.join(",")+"}";}return encode(String(v));}'''
DOCS = r'''function docInfo(d){var p=null;try{p=d.fullName.fsName;}catch(e){}return {id:d.id,name:d.name,path:p,saved:d.saved,width:Number(d.width.as("px")),height:Number(d.height.as("px")),mode:String(d.mode)};}'''


def source(request):
    op = request["operation"]
    if op == "scene_info":
        body = 'var ds=[];for(var i=0;i<app.documents.length;i++)ds.push(docInfo(app.documents[i]));return {version:app.version,documents:ds,active_document_id:app.documents.length?app.activeDocument.id:null};'
    else:
        target = request["document_id"]
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise ValueError("document_id must be a positive integer")
        check = f'if(!app.documents.length||app.activeDocument.id!=={target})throw new Error("Selected document is no longer active; reselect with the user before continuing");'
        if op == "inspect_document":
            body = f'var d=null;for(var j=0;j<app.documents.length;j++)if(app.documents[j].id==={target})d=app.documents[j];if(d===null)throw new Error("Selected document is closed");var count=0;function layers(ls){{var a=[];for(var i=0;i<ls.length&&count<2000;i++){{count++;var l=ls[i],o={{name:l.name,visible:l.visible,typename:l.typename}};if(l.typename==="LayerSet")o.layers=layers(l.layers);a.push(o);}}return a;}}var r=docInfo(d);r.layers=layers(d.layers);r.layer_limit=2000;r.layer_count_returned=count;r.truncated=count>=2000;return r;'
        elif op == "execute_script":
            code = request.get("code")
            if not isinstance(code, str) or not code.strip() or len(code) > 250000:
                raise ValueError("code must contain 1–250000 characters")
            body = check + 'return eval(' + json.dumps(code, ensure_ascii=True) + ');'
        else:
            raise ValueError("Unsupported operation")
    deadline = request.get('expires_at', time.time() + 20)
    if not isinstance(deadline, (int, float)) or deadline <= time.time():
        raise ValueError('Request expired before Photoshop execution; not executed')
    body = 'if(new Date().getTime()>' + str(int(deadline * 1000)) + ')throw new Error("Request expired before Photoshop execution; not executed");' + body
    return '(function(){' + SERIALIZER + DOCS + 'try{return encode({ok:true,data:(function(){' + body + '})()});}catch(e){return encode({ok:false,error:{code:"photoshop_script_error",message:String(e)}});}})();'


def execute(request):
    import pythoncom
    import win32com.client.dynamic
    selected = select(discover(), request.get("session_id"))
    pythoncom.CoInitialize()
    try:
        app = win32com.client.dynamic.Dispatch(pythoncom.GetActiveObject(selected["prog_id"]).QueryInterface(pythoncom.IID_IDispatch))
        # Validate the object instead of trusting the version-independent alias.
        actual_dir = os.path.normcase(os.path.abspath(str(app.Path)))
        expected_dir = os.path.normcase(os.path.dirname(selected["executable"]))
        if actual_dir != expected_dir:
            raise RuntimeError("COM returned a different Photoshop installation; refusing operation")
        version = str(app.Version)
        if tuple(int(x) for x in version.split(".")[:2]) < (26, 2):
            raise RuntimeError("Photoshop 26.2 or later is required")
        if version.split('.')[0] != str(selected.get("version", "")).split('.')[0]:
            raise RuntimeError("COM version differs from the selected executable version")
        # Recheck process identity immediately before execution; never reroute on stale PID.
        select(discover(), selected["session_id"])
        response = json.loads(app.DoJavaScript(source(request)))
        response["session_id"] = selected["session_id"]
        return response
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    try:
        result = execute(json.load(sys.stdin))
    except Exception as exc:
        result = failure("native_connection_error", str(exc))
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


