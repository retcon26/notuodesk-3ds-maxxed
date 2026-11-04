/*
    NotuoDesk 3ds Maxxed - Max to Blender exporter
    Run inside 3ds Max:  Scripting > Run Script... > max_to_blender.ms

    Exports to FBX with settings that NotuoDesk 3ds Maxxed's
    "File > Import > FBX from 3ds Max" expects (Z up, centimeters,
    smoothing groups, animation, cameras, lights, embedded textures).

    * "Export Current Scene" writes <scene name>.fbx next to the .max file
    * "Batch Export Folder" converts every .max file in a folder
      (your open scene is not touched until you confirm)
*/

fn maxxedSetFbxParams =
(
    FBXExporterSetParam "ResetExport"
    FBXExporterSetParam "SmoothingGroups" true
    FBXExporterSetParam "TangentSpaceExport" true
    FBXExporterSetParam "Triangulate" false
    FBXExporterSetParam "Animation" true
    FBXExporterSetParam "BakeAnimation" true
    FBXExporterSetParam "Skin" true
    FBXExporterSetParam "Shape" true
    FBXExporterSetParam "Cameras" true
    FBXExporterSetParam "Lights" true
    FBXExporterSetParam "EmbedTextures" true
    FBXExporterSetParam "UpAxis" "Z"
    FBXExporterSetParam "ConvertUnit" "cm"
    FBXExporterSetParam "ASCII" false
)

fn maxxedExportScene outPath =
(
    maxxedSetFbxParams()
    exportFile outPath #noPrompt using:FBXEXP
)

rollout maxxedRollout "3ds Max > Blender" width:240
(
    label lbl1 "NotuoDesk 3ds Maxxed" align:#center
    button btnScene "Export Current Scene" width:200 height:28
    button btnBatch "Batch Export Folder..." width:200 height:28
    label lblStatus "" align:#center

    on btnScene pressed do
    (
        if maxFilePath == "" then
            messageBox "Save the scene first, so the FBX can be written next to it." title:"3ds Maxxed"
        else
        (
            local outPath = maxFilePath + getFilenameFile maxFileName + ".fbx"
            maxxedExportScene outPath
            lblStatus.text = "Saved " + (filenameFromPath outPath)
        )
    )

    on btnBatch pressed do
    (
        local dir = getSavePath caption:"Folder with .max files"
        if dir != undefined do
        (
            local files = getFiles (dir + "\\*.max")
            if files.count == 0 then messageBox "No .max files in that folder." title:"3ds Maxxed"
            else if queryBox ("Convert " + files.count as string + " files to FBX?\nThe current scene will be closed (you'll be asked to save it).") title:"3ds Maxxed" do
            (
                if checkForSave() do
                (
                    local done = 0
                    for f in files do
                    (
                        if loadMaxFile f quiet:true do
                        (
                            maxxedExportScene (getFilenamePath f + getFilenameFile f + ".fbx")
                            done += 1
                            lblStatus.text = (done as string) + " / " + (files.count as string)
                        )
                    )
                    resetMaxFile #noPrompt
                    messageBox ("Exported " + done as string + " of " + files.count as string + " files.") title:"3ds Maxxed"
                )
            )
        )
    )
)

createDialog maxxedRollout
