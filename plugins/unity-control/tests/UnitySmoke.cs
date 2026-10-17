// Copied only into a newly created scratch project by editor_smoke.py.
using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using Bubble.UnityControl;
using UnityEditor;
using UnityEngine;

public static class BubbleSmoke
{
    static int mainThread;
    static volatile bool complete;
    static string failure;
    public static string Echo(string value)
    {
        if (Thread.CurrentThread.ManagedThreadId != mainThread) throw new Exception("Not on main thread");
        return "echo:" + value;
    }
    public static string Throw() { throw new InvalidOperationException("expected smoke exception"); }
    public static void Run()
    {
        mainThread = Thread.CurrentThread.ManagedThreadId;
        Bridge.Start();
        EditorApplication.update += Finish;
        new Thread(Check) { IsBackground = true }.Start();
    }
    static Bridge.Response Send(Bridge.Session session, string operation, Bridge.Args arguments = null, double expiry = 0, string credential = null)
    {
        var request = new Bridge.Request { protocol = 1, token = credential ?? session.token, operation = operation, arguments = arguments, timeout = 10, expires_at = expiry == 0 ? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 + 10 : expiry };
        using (var client = new TcpClient("127.0.0.1", session.port))
        using (var stream = client.GetStream())
        {
            client.ReceiveTimeout = 15000;
            byte[] bytes = Encoding.UTF8.GetBytes(JsonUtility.ToJson(request) + "\n");
            stream.Write(bytes, 0, bytes.Length);
            using (var reader = new StreamReader(stream)) return JsonUtility.FromJson<Bridge.Response>(reader.ReadLine());
        }
    }
    static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    static void Check()
    {
        try
        {
            string path = Path.Combine(Environment.GetEnvironmentVariable("BUBBLE_UNITY_SESSION_DIR"), System.Diagnostics.Process.GetCurrentProcess().Id + ".json");
            var session = JsonUtility.FromJson<Bridge.Session>(File.ReadAllText(path));
            var status = Send(session, "status");
            Require(status.ok && status.data.unity_version.StartsWith("6000."), "status failed");
            var scene = Send(session, "scene_info");
            Require(scene.ok && scene.data.project == session.project, "scene project mismatch");
            var auth = Send(session, "invoke_method", new Bridge.Args { type_name = "BubbleSmoke", method_name = "Echo", with_payload = true, payload = "SHOULD NOT RUN" }, credential: "wrong");
            Require(!auth.ok && auth.error.code == "authentication_failed", "authentication bypass");
            var expired = Send(session, "invoke_method", new Bridge.Args { type_name = "BubbleSmoke", method_name = "Echo" }, expiry: 1);
            Require(!expired.ok && expired.error.code == "expired", "expired work executed");
            var echo = Send(session, "invoke_method", new Bridge.Args { type_name = "BubbleSmoke", method_name = "Echo", with_payload = true, payload = "你好 Unity" });
            Require(echo.ok && echo.data.result == "echo:你好 Unity", "main-thread method failed");
            var error = Send(session, "invoke_method", new Bridge.Args { type_name = "BubbleSmoke", method_name = "Throw" });
            Require(!error.ok && error.error.execution_uncertain, "script error not surfaced");
            var inspect = Send(session, "inspect_scene", new Bridge.Args { max_objects = 100 });
            Require(inspect.ok && !inspect.data.truncated, "inspection failed");
            var unknown = Send(session, "unknown_operation");
            Require(!unknown.ok && unknown.error.code == "unknown_operation", "unknown operation accepted");
        }
        catch (Exception error) { failure = error.ToString(); }
        finally { complete = true; }
    }
    static void Finish()
    {
        if (!complete) return;
        EditorApplication.update -= Finish;
        Bridge.Stop();
        File.WriteAllText(Environment.GetEnvironmentVariable("BUBBLE_UNITY_SMOKE_RESULT"), failure ?? "PASS: Unity status, scene, auth, expiry, main-thread C# invocation, exception and inspection");
        EditorApplication.Exit(failure == null ? 0 : 1);
    }
}
