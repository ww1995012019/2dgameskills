// Unity editor importer for animations.json. Put this file in Assets/Editor/, copy atlas*.png and
// animations.json into your project, select animations.json and run
// Tools > Sprite Set > Import Selected. Creates sliced sprites and one .anim per clip.
// Requires com.unity.nuget.newtonsoft-json (bundled with most templates).
#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

public static class SpriteSetImporter
{
    [MenuItem("Tools/Sprite Set/Import Selected")]
    static void Import()
    {
        var json = AssetDatabase.GetAssetPath(Selection.activeObject);
        if (!json.EndsWith(".json")) { Debug.LogError("Select animations.json"); return; }
        var dir = Path.GetDirectoryName(json);
        var doc = JObject.Parse(File.ReadAllText(json));
        int size = (int)doc["frame_size"];
        var pivot = doc["pivot"].ToObject<float[]>();
        var pages = doc["pages"].ToArray();
        var regions = doc["regions"].ToArray();

        var names = new string[regions.Length];
        for (int p = 0; p < pages.Length; p++)
        {
            var path = Path.Combine(dir, (string)pages[p]["file"]).Replace('\\', '/');
            var ti = (TextureImporter)AssetImporter.GetAtPath(path);
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Multiple;
            ti.mipmapEnabled = false;
            ti.alphaIsTransparency = true;
            ti.maxTextureSize = 8192;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            int h = (int)pages[p]["h"];
            var metas = new List<SpriteMetaData>();
            for (int i = 0; i < regions.Length; i++)
            {
                var r = regions[i];
                if ((int)r["page"] != p) continue;
                int rw = (int)r["w"], rh = (int)r["h"];
                names[i] = "r" + i;
                metas.Add(new SpriteMetaData
                {
                    name = names[i],
                    rect = new Rect((int)r["x"], h - (int)r["y"] - rh, rw, rh),
                    alignment = (int)SpriteAlignment.Custom,
                    // Keep every sprite on the shared feet pivot despite trimming.
                    pivot = new Vector2((pivot[0] - (int)r["ox"]) / rw, 1f - (pivot[1] - (int)r["oy"]) / rh),
                });
            }
#pragma warning disable 0618
            ti.spritesheet = metas.ToArray();
#pragma warning restore 0618
            ti.SaveAndReimport();
        }

        var sprites = new Dictionary<string, Sprite>();
        foreach (var page in pages)
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(Path.Combine(dir, (string)page["file"]).Replace('\\', '/')))
                if (o is Sprite s) sprites[s.name] = s;

        foreach (var kv in (JObject)doc["clips"])
        {
            var c = (JObject)kv.Value;
            float fps = (float)c["fps"];
            var refs = c["frames"].ToObject<int[]>();
            var clip = new AnimationClip { frameRate = fps };
            var keys = refs.Select((r, i) => new ObjectReferenceKeyframe { time = i / fps, value = sprites[names[r]] }).ToList();
            // Extra key so the final frame gets its full duration.
            keys.Add(new ObjectReferenceKeyframe { time = refs.Length / fps, value = sprites[names[refs[refs.Length - 1]]] });
            var binding = new EditorCurveBinding { type = typeof(SpriteRenderer), path = "", propertyName = "m_Sprite" };
            AnimationUtility.SetObjectReferenceCurve(clip, binding, keys.ToArray());
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = (bool)c["loop"];
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            var events = new List<AnimationEvent>();
            foreach (var e in c["events"])
                events.Add(new AnimationEvent { time = (int)e["frame"] / fps, functionName = "OnSpriteEvent", stringParameter = (string)e["name"] });
            AnimationUtility.SetAnimationEvents(clip, events.ToArray());
            AssetDatabase.CreateAsset(clip, Path.Combine(dir, kv.Key + ".anim").Replace('\\', '/'));
        }
        AssetDatabase.SaveAssets();
        Debug.Log($"Imported {doc["clips"].Count()} clips");
    }
}
#endif
