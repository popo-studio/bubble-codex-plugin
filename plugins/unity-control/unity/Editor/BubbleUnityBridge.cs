// Editor-only, authenticated loopback bridge. No third-party Unity dependencies.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Bubble.UnityControl
{
    [InitializeOnLoad]
    public static class Bridge
    {
        const int MaxMessage = 1024 * 1024;
        static readonly object Gate = new object();
        static readonly Queue<Job> Jobs = new Queue<Job>();
        static readonly SemaphoreSlim Connections = new SemaphoreSlim(8);
        static TcpListener listener;
        static string token, recordPath, projectPath;
        static int pid;
        static volatile bool closed = true;

        [Serializable] public class Args { public string type_name, method_name, payload, menu_path; public bool with_payload; public int max_objects = 5000; }
        [Serializable] public class Request { public int protocol; public string token, operation; public Args arguments; public double timeout, expires_at; }
        [Serializable] public class Error { public string code, message; public bool execution_uncertain; }
        [Serializable] public class Response { public bool ok; public Data data; public Error error; }
        [Serializable] public class Session { public int protocol = 1, port, pid; public string host = "127.0.0.1", token, unity_version, project; }
        [Serializable] public class SceneRow { public string path, name; public bool modified, loaded; public int root_count; }
        [Serializable] public class Issue { public string kind, object_path, component, property, asset_path; public int count; }
        [Serializable] public class Data
        {
            public string path, project, project_name, unity_version, result, result_type, note;
            public int pid, inspected_objects;
            public bool modified, is_playing, is_compiling, is_updating, truncated, executed;
            public SceneRow[] scenes;
            public string[] selection;
            public Issue[] issues;
        }
        sealed class Job
        {
            public Request Request;
            public Response Response;
            public readonly ManualResetEventSlim Done = new ManualResetEventSlim();
            public bool Running, Cancelled;
        }

        static Bridge()
        {
            EditorApplication.update += Update;
            EditorApplication.quitting += Stop;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.playModeStateChanged += state => {
                if (state == PlayModeStateChange.ExitingEditMode) Stop();
                if (state == PlayModeStateChange.EnteredEditMode) Start();
            };
            EditorApplication.delayCall += Start;
        }

        [MenuItem("Tools/Bubble/Start Unity Bridge")]
        public static void Start()
        {
            if (!closed || EditorApplication.isPlayingOrWillChangePlaymode) return;
            if (Application.platform != RuntimePlatform.WindowsEditor)
            {
                Debug.LogWarning("Bubble Unity 0.1.1 supports Windows Editor only; bridge was not started.");
                return;
            }
            if (Application.isBatchMode && Environment.GetEnvironmentVariable("BUBBLE_UNITY_ALLOW_BATCH") != "1") return;
            try
            {
                projectPath = Directory.GetParent(Application.dataPath).FullName;
                pid = System.Diagnostics.Process.GetCurrentProcess().Id;
                byte[] secret = new byte[32];
                using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(secret);
                token = BitConverter.ToString(secret).Replace("-", "").ToLowerInvariant();
                string directory = Environment.GetEnvironmentVariable("BUBBLE_UNITY_SESSION_DIR");
                if (String.IsNullOrEmpty(directory)) directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".bubble-unity", "sessions");
                Directory.CreateDirectory(directory);
                recordPath = Path.Combine(directory, pid + ".json");
                listener = new TcpListener(IPAddress.Loopback, 0);
                listener.Start(8);
                closed = false;
                var record = new Session { pid = pid, port = ((IPEndPoint)listener.LocalEndpoint).Port, token = token, unity_version = Application.unityVersion, project = projectPath };
                string temporary = recordPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
                try
                {
                    File.WriteAllText(temporary, JsonUtility.ToJson(record), new UTF8Encoding(false));
                    if (File.Exists(recordPath)) File.Replace(temporary, recordPath, null);
                    else File.Move(temporary, recordPath);
                }
                finally { if (File.Exists(temporary)) File.Delete(temporary); }
                var localListener = listener;
                var localToken = token;
                new Thread(() => Accept(localListener, localToken)) { IsBackground = true, Name = "Bubble Unity Bridge" }.Start();
            }
            catch (Exception error) { Stop(); Debug.LogWarning("Bubble Unity bridge: " + error.Message); }
        }

        [MenuItem("Tools/Bubble/Stop Unity Bridge")]
        public static void Stop()
        {
            closed = true;
            listener?.Stop();
            listener = null;
            lock (Gate)
            {
                while (Jobs.Count > 0)
                {
                    var job = Jobs.Dequeue();
                    job.Cancelled = true;
                    job.Response = Fail("bridge_stopped", "Bridge stopped before execution.");
                    job.Done.Set();
                }
            }
            try { if (!String.IsNullOrEmpty(recordPath) && File.Exists(recordPath)) File.Delete(recordPath); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        static double Now() { return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0; }
        static Response Fail(string code, string message, bool uncertain = false) { return new Response { ok = false, error = new Error { code = code, message = message, execution_uncertain = uncertain } }; }
        static bool Auth(string left, string right)
        {
            if (left == null || right == null || left.Length != right.Length) return false;
            int difference = 0;
            for (int i = 0; i < left.Length; i++) difference |= left[i] ^ right[i];
            return difference == 0;
        }
        static void Accept(TcpListener localListener, string localToken)
        {
            while (!closed && ReferenceEquals(listener, localListener))
            {
                TcpClient client;
                try { client = localListener.AcceptTcpClient(); }
                catch (SocketException) { break; }
                catch (ObjectDisposedException) { break; }
                if (!Connections.Wait(0)) { client.Close(); continue; }
                ThreadPool.QueueUserWorkItem(_ => {
                    try { Handle(client, localListener, localToken); }
                    finally { client.Close(); Connections.Release(); }
                });
            }
        }
        static void Handle(TcpClient client, TcpListener generation, string localToken)
        {
            try
            {
                client.ReceiveTimeout = 5000;
                client.SendTimeout = 5000;
                using (var stream = client.GetStream())
                {
                    var bytes = new List<byte>();
                    var chunk = new byte[4096];
                    bool ended = false;
                    while (!ended && bytes.Count <= MaxMessage)
                    {
                        int count = stream.Read(chunk, 0, chunk.Length);
                        if (count == 0) return;
                        for (int i = 0; i < count; i++)
                        {
                            if (chunk[i] == 10) { ended = true; break; }
                            bytes.Add(chunk[i]);
                        }
                    }
                    Response response;
                    if (!ended || bytes.Count >= MaxMessage) response = Fail("request_too_large", "Request must be one JSON line under 1 MiB.");
                    else
                    {
                        try { response = Invoke(JsonUtility.FromJson<Request>(Encoding.UTF8.GetString(bytes.ToArray())), generation, localToken); }
                        catch (Exception error) { response = Fail("invalid_request", error.Message); }
                    }
                    byte[] reply = Encoding.UTF8.GetBytes(JsonUtility.ToJson(response) + "\n");
                    if (reply.Length > MaxMessage) reply = Encoding.UTF8.GetBytes(JsonUtility.ToJson(Fail("response_too_large", "Response exceeded 1 MiB. Operation may have completed; do not retry automatically.", true)) + "\n");
                    stream.Write(reply, 0, reply.Length);
                }
            }
            catch (IOException) { }
            catch (SocketException) { }
            catch (ObjectDisposedException) { }
        }
        static Response Invoke(Request request, TcpListener generation, string localToken)
        {
            if (request == null || request.protocol != 1 || !Auth(request.token, localToken)) return Fail("authentication_failed", "Invalid bridge credentials or protocol.");
            if (!(request.timeout > 0 && request.timeout <= 120) || Double.IsNaN(request.expires_at) || Double.IsInfinity(request.expires_at)) return Fail("invalid_timeout", "Timeout must be finite and in (0,120].");
            double remaining = Math.Min(request.timeout, request.expires_at - Now());
            if (remaining <= 0) return Fail("expired", "Request expired before scheduling.");
            if (request.operation != "status" && request.operation != "scene_info" && request.operation != "inspect_scene" && request.operation != "invoke_method" && request.operation != "execute_menu") return Fail("unknown_operation", "Unknown operation.");
            var job = new Job { Request = request };
            lock (Gate)
            {
                if (closed || !ReferenceEquals(listener, generation)) return Fail("bridge_stopped", "Bridge generation is no longer active.");
                if (Jobs.Count >= 32) return Fail("busy", "Main-thread queue is full; no work scheduled.");
                Jobs.Enqueue(job);
            }
            if (job.Done.Wait(TimeSpan.FromSeconds(remaining))) return job.Response;
            lock (Gate)
            {
                if (job.Done.IsSet) return job.Response;
                job.Cancelled = true;
                return Fail("timeout", job.Running ? "Execution started and may still complete. Do not retry automatically." : "Timed out in queue; cancelled before execution.", job.Running);
            }
        }
        static void Update()
        {
            Job job;
            lock (Gate)
            {
                if (closed || Jobs.Count == 0) return;
                job = Jobs.Dequeue();
                if (job.Cancelled || job.Request.expires_at <= Now())
                {
                    job.Response = Fail("expired", "Request cancelled before execution.");
                    job.Done.Set();
                    return;
                }
                job.Running = true;
            }
            try { job.Response = Dispatch(job.Request); }
            catch (Exception error)
            {
                var cause = error is TargetInvocationException && error.InnerException != null ? error.InnerException : error;
                bool mutation = job.Request.operation == "invoke_method" || job.Request.operation == "execute_menu";
                job.Response = Fail("execution_error", cause.GetType().Name + ": " + cause.Message, mutation);
            }
            finally { job.Done.Set(); }
        }
        static Data Info()
        {
            var active = SceneManager.GetActiveScene();
            var scenes = new List<SceneRow>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                var scene = SceneManager.GetSceneAt(i);
                scenes.Add(new SceneRow { path = scene.path, name = scene.name, modified = scene.isDirty, loaded = scene.isLoaded, root_count = scene.rootCount });
            }
            return new Data { path = active.path ?? "", modified = active.isDirty, scenes = scenes.ToArray(), project = projectPath, project_name = Path.GetFileName(projectPath), unity_version = Application.unityVersion, pid = pid, is_playing = EditorApplication.isPlayingOrWillChangePlaymode, is_compiling = EditorApplication.isCompiling, is_updating = EditorApplication.isUpdating, selection = Selection.objects.Select(item => item.name).ToArray() };
        }
        static Response Dispatch(Request request)
        {
            var data = Info();
            var args = request.arguments ?? new Args();
            if (request.operation == "status" || request.operation == "scene_info") return new Response { ok = true, data = data };
            if (data.is_compiling || data.is_updating || data.is_playing) return Fail("editor_busy", "Wait for Edit Mode, script compilation and asset import to finish. No operation executed.");
            if (request.operation == "inspect_scene") Inspect(data, args.max_objects);
            else if (request.operation == "execute_menu")
            {
                if (String.IsNullOrWhiteSpace(args.menu_path)) return Fail("invalid_arguments", "menu_path is required.");
                data.executed = EditorApplication.ExecuteMenuItem(args.menu_path);
                if (!data.executed) return Fail("menu_unavailable", "Menu command was unavailable or rejected.");
                data.note = "Menu command dispatched; asynchronous effects or dialogs may continue. Do not repeat automatically.";
            }
            else if (request.operation == "invoke_method")
            {
                if (String.IsNullOrWhiteSpace(args.type_name) || String.IsNullOrWhiteSpace(args.method_name)) return Fail("invalid_arguments", "Exact fully qualified type_name and method_name are required.");
                var types = AppDomain.CurrentDomain.GetAssemblies().Select(assembly => assembly.GetType(args.type_name, false)).Where(type => type != null).ToArray();
                if (types.Length != 1) return Fail("method_selection", "Type is missing or ambiguous across loaded assemblies; use a unique fully qualified type name.");
                var method = types[0].GetMethod(args.method_name, BindingFlags.Public | BindingFlags.Static, null, args.with_payload ? new[] { typeof(string) } : Type.EmptyTypes, null);
                if (method == null || method.ContainsGenericParameters) return Fail("method_selection", "Requires a public static non-generic method with no arguments, or one string argument when with_payload=true.");
                if (method.IsDefined(typeof(System.Runtime.CompilerServices.AsyncStateMachineAttribute), false)) return Fail("unsupported_async_method", "Async methods, including async void, are not supported. Use a synchronous Editor entrypoint.");
                Type resultType = method.ReturnType;
                if (resultType != typeof(void) && resultType != typeof(string) && !resultType.IsPrimitive && !resultType.IsEnum && resultType != typeof(decimal)) return Fail("unsupported_return_type", "Method must return void, string, enum or a primitive value. Return serialized JSON as a string for structured results. Task/coroutine methods are not supported.");
                object result = method.Invoke(null, args.with_payload ? new object[] { args.payload ?? "" } : null);
                data.result = result == null ? null : Convert.ToString(result, CultureInfo.InvariantCulture);
                data.result_type = resultType.FullName;
                data.executed = true;
                data.note = "Executed on the Unity Editor main thread with full user privileges. Unity Console logs are not captured.";
            }
            return new Response { ok = true, data = data };
        }
        static string ObjectPath(Transform transform)
        {
            var parts = new List<string>();
            while (transform != null) { parts.Add(transform.name); transform = transform.parent; }
            parts.Reverse();
            return String.Join("/", parts);
        }
        static void Inspect(Data data, int maxObjects)
        {
            if (maxObjects <= 0 || maxObjects > 10000) throw new ArgumentException("max_objects must be between 1 and 10000");
            var issues = new List<Issue>();
            var pending = new Queue<GameObject>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                var scene = SceneManager.GetSceneAt(i);
                if (scene.isLoaded) foreach (var root in scene.GetRootGameObjects()) pending.Enqueue(root);
            }
            while (pending.Count > 0 && data.inspected_objects < maxObjects && issues.Count < 5000)
            {
                var go = pending.Dequeue();
                data.inspected_objects++;
                string path = go.scene.path + ":" + ObjectPath(go.transform);
                int count = GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(go);
                if (count > 0) issues.Add(new Issue { kind = "missing_script", object_path = path, count = count });
                foreach (var component in go.GetComponents<Component>())
                {
                    if (component == null) continue;
                    using (var serialized = new SerializedObject(component))
                    {
                        var property = serialized.GetIterator();
                        while (property.Next(true))
                        {
                            if (property.propertyType == SerializedPropertyType.ObjectReference && property.objectReferenceValue == null && property.objectReferenceInstanceIDValue != 0)
                                issues.Add(new Issue { kind = "missing_reference", object_path = path, component = component.GetType().FullName, property = property.propertyPath });
                            if (issues.Count >= 5000) break;
                        }
                    }
                    if (issues.Count >= 5000) break;
                }
                foreach (Transform child in go.transform) pending.Enqueue(child.gameObject);
            }
            data.truncated = pending.Count > 0 || issues.Count >= 5000;
            data.issues = issues.ToArray();
            data.note = "Read-only scan of loaded scenes: missing scripts and serialized object references. No scene saving, asset import or fixes. Not a complete project/dependency audit; unloaded scenes, prefabs, addressables and external files are excluded.";
        }
    }
}
