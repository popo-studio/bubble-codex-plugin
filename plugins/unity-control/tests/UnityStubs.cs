// Minimal test doubles, NEVER shipped into the Unity runtime package.
// Real Unity API signatures are independently checked by editor_smoke.py.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;

namespace UnityEngine
{
    public enum RuntimePlatform { WindowsEditor, LinuxEditor }
    public class Object { public string name = "Test"; }
    public class Component : Object { }
    public class Transform : Component, IEnumerable<Transform>
    {
        public Transform parent;
        public GameObject gameObject;
        public IEnumerator<Transform> GetEnumerator() { return new List<Transform>().GetEnumerator(); }
        IEnumerator IEnumerable.GetEnumerator() { return GetEnumerator(); }
    }
    public class GameObject : Object
    {
        public Transform transform = new Transform();
        public SceneManagement.Scene scene = new SceneManagement.Scene();
        public T[] GetComponents<T>() { return new T[0]; }
    }
    public static class Application
    {
        public static string dataPath = Path.Combine(Environment.GetEnvironmentVariable("BUBBLE_UNITY_TEST_PROJECT"), "Assets");
        public static string unityVersion = "6000.1.stub";
        public static bool isBatchMode = false;
        public static RuntimePlatform platform = RuntimePlatform.WindowsEditor;
    }
    public static class Debug { public static void LogWarning(string value) { Console.Error.WriteLine(value); } }
    public static class JsonUtility
    {
        public static string ToJson(object value) { return new JavaScriptSerializer().Serialize(value); }
        public static T FromJson<T>(string value) { return new JavaScriptSerializer().Deserialize<T>(value); }
    }
}
namespace UnityEngine.SceneManagement
{
    public struct Scene
    {
        public string path { get { return "Assets/Scenes/Main.unity"; } }
        public string name { get { return "Main"; } }
        public bool isDirty { get { return false; } }
        public bool isLoaded { get { return true; } }
        public int rootCount { get { return 0; } }
        public UnityEngine.GameObject[] GetRootGameObjects() { return new UnityEngine.GameObject[0]; }
    }
    public static class SceneManager
    {
        public static int sceneCount = 1;
        public static Scene GetActiveScene() { return new Scene(); }
        public static Scene GetSceneAt(int index) { return new Scene(); }
    }
}
namespace UnityEditor
{
    public class InitializeOnLoadAttribute : Attribute { }
    public class MenuItem : Attribute { public MenuItem(string path) { } }
    public enum PlayModeStateChange { ExitingEditMode, EnteredPlayMode, ExitingPlayMode, EnteredEditMode }
    public static class EditorApplication
    {
        public static event Action update, quitting;
        public static event Action delayCall;
        public static event Action<PlayModeStateChange> playModeStateChanged;
        public static bool isPlayingOrWillChangePlaymode, isCompiling, isUpdating;
        public static bool ExecuteMenuItem(string path) { return path == "Test/Okay"; }
        public static void Tick()
        {
            if (delayCall != null) { var action = delayCall; delayCall = null; action(); }
            update?.Invoke();
        }
        public static void Quit() { quitting?.Invoke(); }
        public static void Play(PlayModeStateChange state) { playModeStateChanged?.Invoke(state); }
    }
    public static class AssemblyReloadEvents
    {
        public static event Action beforeAssemblyReload;
        public static void Reload() { beforeAssemblyReload?.Invoke(); }
    }
    public static class Selection { public static UnityEngine.Object[] objects = new UnityEngine.Object[0]; }
    public static class GameObjectUtility { public static int GetMonoBehavioursWithMissingScriptCount(UnityEngine.GameObject go) { return 0; } }
    public enum SerializedPropertyType { ObjectReference }
    public class SerializedProperty
    {
        public SerializedPropertyType propertyType;
        public UnityEngine.Object objectReferenceValue;
        public int objectReferenceInstanceIDValue;
        public string propertyPath;
        public bool Next(bool enterChildren) { return false; }
    }
    public class SerializedObject : IDisposable
    {
        public SerializedObject(UnityEngine.Component component) { }
        public SerializedProperty GetIterator() { return new SerializedProperty(); }
        public void Dispose() { }
    }
}
public static class BubbleHarness
{
    static int counter, mainThread;
    public static string Echo(string value)
    {
        if (Thread.CurrentThread.ManagedThreadId != mainThread) throw new Exception("Wrong execution thread");
        return value;
    }
    public static int Increment() { return ++counter; }
    public static int Count() { return counter; }
    public static void Pause(string milliseconds)
    {
        File.WriteAllText(Path.Combine(Environment.GetEnvironmentVariable("BUBBLE_UNITY_TEST_PROJECT"), "pause-started"), "yes");
        Thread.Sleep(Int32.Parse(milliseconds));
    }
    public static void SetCompiling(string value) { UnityEditor.EditorApplication.isCompiling = value == "true"; }
    public static void Reload() { UnityEditor.AssemblyReloadEvents.Reload(); }
    public static void EnterPlay() { UnityEditor.EditorApplication.Play(UnityEditor.PlayModeStateChange.ExitingEditMode); }
    public static void Throw() { throw new InvalidOperationException("expected error"); }
    public static async void AsyncVoid() { await System.Threading.Tasks.Task.Delay(10); counter++; }
    public static void Main()
    {
        mainThread = Thread.CurrentThread.ManagedThreadId;
        Bubble.UnityControl.Bridge.Start();
        while (true) { UnityEditor.EditorApplication.Tick(); Thread.Sleep(2); }
    }
}
