// Minimal test doubles, NEVER shipped into the Unity runtime package.
// Real Unity API signatures are independently checked by editor_smoke.py.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;

namespace UnityEngine
{
    public enum RuntimePlatform { WindowsEditor, LinuxEditor }
    public class Object { static int next; public static Dictionary<int,Object> Registry=new Dictionary<int,Object>(); int id=++next; public string name = "Test"; public Object(){Registry[id]=this;} public int GetInstanceID(){return id;} public static implicit operator bool(Object o){return o!=null;} public static GameObject Instantiate(GameObject o, Transform parent){var n=new GameObject(o.name+" copy");n.transform.parent=parent;return n;} }
    public struct Vector3 { public float x,y,z;public Vector3(float a,float b,float c){x=a;y=b;z=c;} }
    public enum PrimitiveType {Cube,Sphere,Plane,Capsule,Cylinder,Quad}
    public static class QualitySettings {public static string activeColorSpace="Linear";public static int GetQualityLevel(){return 0;}}
    public class Component : Object { }
    public class Transform : Component, IEnumerable<Transform>
    {
        public Transform parent; public Vector3 position,eulerAngles,localScale=new Vector3(1,1,1);
        public GameObject gameObject;
        public IEnumerator<Transform> GetEnumerator() { return UnityEngine.SceneManagement.Scene.Roots.Where(go=>go.transform.parent==this).Select(go=>go.transform).GetEnumerator(); }
        public bool IsChildOf(Transform ancestor){for(var t=this;t!=null;t=t.parent)if(t==ancestor)return true;return false;}
        IEnumerator IEnumerable.GetEnumerator() { return GetEnumerator(); }
    }
    public class GameObject : Object
    {
        public Transform transform = new Transform(); public bool activeSelf=true;
        public bool activeInHierarchy {get{return activeSelf && (!transform.parent || transform.parent.gameObject.activeInHierarchy);}}
        public void SetActive(bool value){activeSelf=value;}
        public GameObject(string n="Test"){name=n;transform.gameObject=this;SceneManagement.Scene.Roots.Add(this);}
        public static GameObject CreatePrimitive(PrimitiveType type){return new GameObject(type.ToString());}
        public SceneManagement.Scene scene = new SceneManagement.Scene();
        public T[] GetComponents<T>() { return new T[0]; }
    }
    public static class Application
    {
        public static string dataPath = Path.Combine(Environment.GetEnvironmentVariable("BUBBLE_UNITY_TEST_PROJECT"), "Assets");
        public static int targetFrameRate=-1;
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
        public static string CurrentPath="Assets/Scenes/Main.unity";public static bool Dirty;public static List<UnityEngine.GameObject> Roots=new List<UnityEngine.GameObject>(); public int instanceHandle;public int handle {get{return instanceHandle==0?1:instanceHandle;}} public bool IsValid(){return true;} public string path { get { return CurrentPath; } }
        public string name { get { return "Main"; } }
        public bool isDirty { get { return Dirty; } }
        public bool isLoaded { get { return true; } }
        public int rootCount { get { return 0; } }
        public UnityEngine.GameObject[] GetRootGameObjects() { return Roots.Where(go=>!go.transform.parent).ToArray(); }
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
    public static class EditorUtility {public static UnityEngine.Object InstanceIDToObject(int id){UnityEngine.Object o;UnityEngine.Object.Registry.TryGetValue(id,out o);return o;} public static bool IsPersistent(UnityEngine.Object o){return false;}}
    public static class Undo {public static void SetTransformParent(UnityEngine.Transform t,UnityEngine.Transform parent,string name){t.parent=parent;}public static void RegisterCreatedObjectUndo(UnityEngine.Object o,string n){} public static void RecordObject(UnityEngine.Object o,string n){} public static void DestroyObjectImmediate(UnityEngine.Object o){UnityEngine.Object.Registry.Remove(o.GetInstanceID());UnityEngine.SceneManagement.Scene.Roots.Remove(o as UnityEngine.GameObject);}}
    public static class PrefabUtility {public static bool IsPartOfPrefabInstance(UnityEngine.Object o){return false;}public static void RecordPrefabInstancePropertyModifications(UnityEngine.Object o){}}
    public class EditorBuildSettingsScene {public string path;}
    public static class EditorBuildSettings {public static EditorBuildSettingsScene[] scenes=new EditorBuildSettingsScene[0];}
    public static class Selection { public static UnityEngine.GameObject activeGameObject; public static UnityEngine.Object[] objects = new UnityEngine.Object[0]; }
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
    public static int PreviewObject(){var go=new UnityEngine.GameObject("Preview");go.scene=new UnityEngine.SceneManagement.Scene{instanceHandle=999};UnityEngine.SceneManagement.Scene.Roots.Remove(go);return go.GetInstanceID();}
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

namespace UnityEditor.SceneManagement {
 using UnityEngine.SceneManagement;
 public enum NewSceneSetup {EmptyScene} public enum NewSceneMode{Single} public enum OpenSceneMode{Single}
 public static class EditorSceneManager {
 public static event Action<Scene,OpenSceneMode> sceneOpened; public static event Action<Scene> sceneClosed; public static event Action<Scene,NewSceneSetup,NewSceneMode> newSceneCreated;
 public static Scene NewScene(NewSceneSetup s,NewSceneMode m){Scene.Roots.Clear();Scene.CurrentPath="";Scene.Dirty=false;var x=new Scene();newSceneCreated?.Invoke(x,s,m);return x;}
 public static Scene OpenScene(string p,OpenSceneMode m){Scene.Roots.Clear();Scene.CurrentPath=p;Scene.Dirty=false;var x=new Scene();sceneOpened?.Invoke(x,m);return x;}
 public static bool SaveScene(Scene s,string p,bool copy){File.WriteAllText(Path.Combine(Directory.GetParent(UnityEngine.Application.dataPath).FullName,p),"fixture");Scene.CurrentPath=p;Scene.Dirty=false;return true;}
 public static bool MarkSceneDirty(Scene s){Scene.Dirty=true;return true;}
 }
}
