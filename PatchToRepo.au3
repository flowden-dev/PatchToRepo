#NoTrayIcon
#pragma compile(Icon, assets\PatchToRepo.ico)
#pragma compile(x64, True)
#pragma compile(Console, False)
#pragma compile(ExecLevel, asInvoker)
#pragma compile(FileVersion, 1.0.4.0)
#pragma compile(ProductVersion, 1.0.4.0)
#pragma compile(FileDescription, Patch to Repo)
#pragma compile(ProductName, Patch to Repo)
#AutoIt3Wrapper_UseX64=y
#AutoIt3Wrapper_Icon=assets\PatchToRepo.ico
#AutoIt3Wrapper_Res_Description=Patch to Repo
#AutoIt3Wrapper_Res_Fileversion=1.0.4.0
#AutoIt3Wrapper_Res_ProductName=Patch to Repo
#AutoIt3Wrapper_Res_RequestedExecutionLevel=asInvoker
#AutoIt3Wrapper_Run_Au3Check=y
#AutoIt3Wrapper_Au3Check_Parameters=-w 3 -w 4 -w 5 -w 6

; Patch to Repo 1.0.4 | AutoIt 3.3.16.1+ | Windows 10 x64
; Run once to install the per-user .patch context menu. No administrator needed.
; Git applies to the working tree only: no staging, commits, pushes or resets.

#include <AutoItConstants.au3>
#include <ButtonConstants.au3>
#include <ComboConstants.au3>
#include <EditConstants.au3>
#include <File.au3>
#include <FileConstants.au3>
#include <GUIConstantsEx.au3>
#include <GuiComboBox.au3>
#include <GuiEdit.au3>
#include <Misc.au3>
#include <MsgBoxConstants.au3>
#include <ScrollBarsConstants.au3>
#include <StaticConstants.au3>
#include <String.au3>
#include <StructureConstants.au3>
#include <WindowsConstants.au3>

Opt("MustDeclareVars", 1)
Opt("SetExitCode", 1)
Opt("WinTitleMatchMode", 3)

Global Const $APP_TITLE = "Patch to Repo"
Global Const $APP_DIR = @LocalAppDataDir & "\PatchToRepo"
Global Const $MAX_RECENT = 20
Global Const $MAX_LOG = 4000000
Global Const $EXEC_OUTPUT_ERROR = -2 ; child succeeded, captured output unavailable
Global Const $INSTANCE_PROPERTY = "PatchToRepo.Instance.50545231"
Global $g_sHive = "HKCU"
If @OSArch = "X64" Then $g_sHive = "HKCU64"
Global Const $SETTINGS = $g_sHive & "\Software\PatchToRepo"
Global Const $MENU_KEY = $g_sHive & "\Software\Classes\SystemFileAssociations\.patch\shell\PatchToRepo"
Global $g_hGUI = 0, $g_bBusy = False, $g_sIncoming = "", $g_sGit = ""
Global $g_iQueuedAction = 0
Global $g_sActionPatch = "", $g_sActionRepo = ""
Global $g_sLog = "", $g_sTempDir = "", $g_sSnapshot = "", $g_iCommand = 0
Global $g_hSnapshot = 0, $g_iOperation = 0
Global $g_bWarnings = False, $g_bTesting = False
Global $g_iTestCount = 0, $g_iTestFailed = 0, $g_sTestKey = ""
Global $g_idPatch = 0, $g_idRepo = 0, $g_idStatus = 0, $g_idLog = 0
Global $g_idBrowsePatch = 0, $g_idBrowseRepo = 0, $g_idForget = 0
Global $g_idCheck = 0, $g_idApply = 0, $g_idClose = 0, $g_idAutoClose = 0
Global $g_idGit = 0, $g_idInstall = 0, $g_idUninstall = 0, $g_idCopy = 0, $g_idFolder = 0
Global $g_idInstallButton = 0, $g_idUninstallButton = 0
Global $g_aRecent[0]

; Test mode uses disposable files/registry keys; no real integration or settings.
If $CmdLine[0] = 1 Then
    If $CmdLine[1] = "--self-test" Then Exit _SelfTest()
EndIf

_Main()

Func _Main()
    Local $sPatch = "", $bUninstall = False
    Switch $CmdLine[0]
        Case 0
        Case 1
            Switch StringLower($CmdLine[1])
                Case "--install"
                Case "--uninstall"
                    $bUninstall = True
                Case Else
                    If StringLeft($CmdLine[1], 2) = "--" Then _UsageError()
                    $sPatch = _CleanPath($CmdLine[1])
            EndSwitch
        Case 2
            If $CmdLine[1] <> "--apply" Then _UsageError()
            $sPatch = _CleanPath($CmdLine[2])
        Case Else
            _UsageError()
    EndSwitch

    ; One active window prevents overlapping applies and lost history updates.
    ; A new Explorer invocation hands its patch to the idle existing window.
    If Not _Singleton("Local\PatchToRepo." & @UserName, 1) Then
        Local $hExisting = _FindInstanceWindow()
        If $hExisting Then WinActivate($hExisting)
        If $sPatch <> "" And $hExisting Then
            If _ForwardPatch($hExisting, $sPatch) Then Exit
        ElseIf Not $bUninstall And $hExisting Then
            Exit
        EndIf
        MsgBox($MB_ICONINFORMATION, $APP_TITLE, "Patch to Repo is already working. Finish that operation, then try again.")
        Exit 1
    EndIf

    If $bUninstall Then
        If _RemoveMenu() Then
            MsgBox($MB_ICONINFORMATION, $APP_TITLE, "The context menu and Start menu shortcuts have been removed." & @CRLF & _
                "Your repository history is kept. See README.md for complete removal.")
            Exit
        EndIf
        Exit 1
    EndIf

    If Not _MakeTempDir() Then
        MsgBox($MB_ICONERROR, $APP_TITLE, "Cannot create a temporary working folder in:" & @CRLF & @TempDir)
        Exit 1
    EndIf
    OnAutoItExitRegister("_Cleanup")
    _CleanGitEnvironment()
    _LoadRecent()
    $g_sGit = _FindGit()

    ; Running with no patch installs/repairs the menu. A context invocation does
    ; not reinstall, overwrite a running EXE, or re-enable a removed menu.
    Local $bInstalled = False
    If $sPatch = "" Then $bInstalled = _InstallMenu()
    _CreateGUI($sPatch)
    If $bInstalled Then
        _Status("Installed. Right-click a .patch file, or choose one above.", 0x176A35)
    Else
        _Status("Select a repository, then Apply patch. Check only makes no changes.")
    EndIf
    If $g_sGit = "" Then _Status("Git was not found. Use 'Locate Git...' to select git.exe.", 0x9B5200)

    While True
        Local $iEvent = GUIGetMsg()
        If $g_iQueuedAction <> 0 And $iEvent <> $g_iQueuedAction Then ContinueLoop
        Switch $iEvent
            Case $GUI_EVENT_NONE
                ; Finish already queued actions against their original patch
                ; before replacing the selection from an Explorer handoff.
                If $g_sIncoming <> "" And Not $g_bBusy Then _UseIncomingPatch()
            Case $GUI_EVENT_CLOSE, $g_idClose
                _SetBusy(True)
                If $g_sIncoming <> "" Then
                    _SetBusy(False)
                    ContinueLoop
                EndIf
                ExitLoop
            Case $g_idBrowsePatch
                _BrowsePatch()
            Case $g_idBrowseRepo
                _BrowseRepo()
            Case $g_idForget
                _ForgetRepo()
            Case $g_idCheck
                If $g_iQueuedAction = $g_idCheck Then
                    $g_iQueuedAction = 0
                    _RunOperation(False, $g_sActionPatch, $g_sActionRepo)
                EndIf
            Case $g_idApply
                If $g_iQueuedAction = $g_idApply Then
                    $g_iQueuedAction = 0
                    _RunOperation(True, $g_sActionPatch, $g_sActionRepo)
                EndIf
            Case $g_idCopy
                If ClipPut($g_sLog) Then
                    _Status("Details copied to the clipboard.")
                Else
                    _Fail("Windows could not update the clipboard. Try Copy details again.")
                EndIf
            Case $g_idGit
                _ChooseGit()
            Case $g_idInstall, $g_idInstallButton
                _SetBusy(True)
                If _InstallMenu() Then _Status("Context menu and Start menu shortcuts installed.", 0x176A35)
                _SetBusy(False)
            Case $g_idUninstall, $g_idUninstallButton
                _SetBusy(True)
                If _RemoveMenu() Then _Status("Uninstalled the context menu and shortcuts. History is kept. Use Install / repair to enable again.", 0x176A35)
                _SetBusy(False)
            Case $g_idFolder
                Local $sOpen = _CleanPath(GUICtrlRead($g_idRepo))
                If _IsDirectory($sOpen) Then ShellExecute($sOpen)
        EndSwitch
    WEnd
    If Not RegWrite($SETTINGS, "CloseAfterSuccess", "REG_DWORD", Number(GUICtrlRead($g_idAutoClose) = $GUI_CHECKED)) Then
        MsgBox($MB_ICONWARNING, $APP_TITLE, "The close-after-success preference could not be saved.", 0, $g_hGUI)
    EndIf
    _DestroyGUI()
EndFunc

Func _UsageError()
    MsgBox($MB_ICONERROR, $APP_TITLE, "Usage: PatchToRepo [--install | --uninstall | --apply PATCH | PATCH]" & @CRLF & _
        "Select one patch at a time.")
    Exit 1
EndFunc

Func _CreateGUI($sPatch, $bShow = True, $bRegisterInstance = True)
    $g_hGUI = GUICreate($APP_TITLE, 820, 575)
    If Not $g_hGUI Then
        MsgBox($MB_ICONERROR, $APP_TITLE, "Windows could not create the repository picker.")
        Exit 1
    EndIf
    If $bRegisterInstance Then
        Local $aProp = DllCall("user32.dll", "bool", "SetPropW", "hwnd", $g_hGUI, "wstr", $INSTANCE_PROPERTY, "handle", @AutoItPID)
        If @error Then Exit 1
        If Not $aProp[0] Then
            MsgBox($MB_ICONERROR, $APP_TITLE, "Windows could not register the repository picker window.")
            Exit 1
        EndIf
    EndIf
    Local $sGUIIcon = @ScriptFullPath
    If Not @Compiled Then $sGUIIcon = @ScriptDir & "\assets\PatchToRepo.ico"
    If FileExists($sGUIIcon) Then GUISetIcon($sGUIIcon, -1, $g_hGUI)
    GUISetFont(10, 400, 0, "Segoe UI", $g_hGUI)
    Local $idMenu = GUICtrlCreateMenu("Setup")
    $g_idGit = GUICtrlCreateMenuItem("Locate Git...", $idMenu)
    $g_idInstall = GUICtrlCreateMenuItem("Install / repair context menu", $idMenu)
    $g_idUninstall = GUICtrlCreateMenuItem("Remove context menu and shortcuts", $idMenu)
    GUICtrlCreateLabel("Apply a patch to a Git repository", 20, 15, 770, 29)
    GUICtrlSetFont(-1, 16, 600)
    GUICtrlCreateLabel("Patch file", 20, 58, 700, 20)
    $g_idPatch = GUICtrlCreateInput($sPatch, 20, 82, 665, 26, BitOR($ES_AUTOHSCROLL, $ES_READONLY))
    $g_idBrowsePatch = GUICtrlCreateButton("Choose patch...", 695, 81, 105, 28)
    GUICtrlCreateLabel("Repository folder - recent repositories are in the drop-down", 20, 123, 780, 20)
    $g_idRepo = GUICtrlCreateCombo("", 20, 147, 550, 240, BitOR($CBS_DROPDOWN, $CBS_AUTOHSCROLL, $WS_VSCROLL))
    _GUICtrlComboBox_SetDroppedWidth($g_idRepo, 760)
    _GUICtrlComboBox_LimitText($g_idRepo, 32700)
    $g_idBrowseRepo = GUICtrlCreateButton("Browse...", 580, 146, 105, 28)
    $g_idForget = GUICtrlCreateButton("Forget path", 695, 146, 105, 28)
    GUICtrlSetTip($g_idForget, "Removes this path from history. Does not delete repository files.")
    Local $sFirst = ""
    If UBound($g_aRecent) Then $sFirst = $g_aRecent[0]
    _RefreshRecent($sFirst)
    $g_idAutoClose = GUICtrlCreateCheckbox("Close after successful apply", 20, 190, 300, 24)
    Local $iClose = RegRead($SETTINGS, "CloseAfterSuccess")
    If @error Then $iClose = 1
    If $iClose Then GUICtrlSetState($g_idAutoClose, $GUI_CHECKED)
    $g_idInstallButton = GUICtrlCreateButton("Install / repair", 580, 187, 105, 28)
    GUICtrlSetTip($g_idInstallButton, "Install or repair the context-menu entry and Start menu shortcuts using this script.")
    $g_idUninstallButton = GUICtrlCreateButton("Uninstall", 695, 187, 105, 28)
    GUICtrlSetTip($g_idUninstallButton, "Remove the context menu and Start menu shortcuts. Keep repository history for reinstalling.")
    GUICtrlCreateLabel("Applies to your working files. Review and commit afterward in your Git app.", 20, 220, 780, 22)
    $g_idStatus = GUICtrlCreateLabel("", 20, 253, 780, 38)
    GUICtrlSetFont($g_idStatus, 10, 600)
    $g_idLog = GUICtrlCreateEdit("", 20, 296, 780, 192, BitOR($ES_READONLY, $ES_MULTILINE, $ES_AUTOVSCROLL, $ES_AUTOHSCROLL, $WS_VSCROLL, $WS_HSCROLL))
    GUICtrlSetFont($g_idLog, 9, 400, 0, "Consolas")
    _GUICtrlEdit_SetLimitText($g_idLog, $MAX_LOG)
    $g_idFolder = GUICtrlCreateButton("Open repo", 20, 507, 105, 32)
    $g_idCopy = GUICtrlCreateButton("Copy details", 135, 507, 105, 32)
    $g_idCheck = GUICtrlCreateButton("Check only", 445, 507, 105, 32)
    $g_idApply = GUICtrlCreateButton("Apply patch", 560, 507, 125, 32, $BS_DEFPUSHBUTTON)
    $g_idClose = GUICtrlCreateButton("Close", 695, 507, 105, 32)
    If Not _ControlsValid() Then
        _SetupError("Windows could not create all picker controls. Close other applications and try again.")
        Exit 1
    EndIf
    If Not GUIRegisterMsg($WM_COPYDATA, "_ReceivePatch") Or Not GUIRegisterMsg($WM_COMMAND, "_QueueAction") Then
        _SetupError("Windows message handling could not be initialized. Close the picker and try again.")
        Exit 1
    EndIf
    If $bShow Then GUISetState(@SW_SHOW, $g_hGUI)
    GUICtrlSetState($g_idApply, $GUI_FOCUS)
EndFunc

Func _ControlsValid()
    Local $aIDs[18] = [$g_idPatch, $g_idRepo, $g_idStatus, $g_idLog, $g_idBrowsePatch, $g_idBrowseRepo, $g_idForget, _
        $g_idCheck, $g_idApply, $g_idClose, $g_idAutoClose, $g_idGit, $g_idInstall, $g_idUninstall, $g_idCopy, $g_idFolder, _
        $g_idInstallButton, $g_idUninstallButton]
    For $id In $aIDs
        If $id = 0 Then Return False
    Next
    Return True
EndFunc

Func _BrowsePatch()
    _SetBusy(True)
    Local $sFile = FileOpenDialog("Choose a patch", "", "Patch files (*.patch;*.diff)|All files (*.*)", $FD_FILEMUSTEXIST, "", $g_hGUI)
    If Not @error Then
        GUICtrlSetData($g_idPatch, $sFile)
        $g_sIncoming = "" ; a later explicit file choice supersedes a pending handoff
        _Status("Patch selected. Choose the target repository, then Apply patch.")
    EndIf
    _SetBusy(False)
EndFunc

Func _BrowseRepo()
    _SetBusy(True)
    Local $sFolder = FileSelectFolder("Choose the Git repository folder", "", 0, GUICtrlRead($g_idRepo), $g_hGUI)
    If Not @error Then ControlSetText($g_hGUI, "", $g_idRepo, $sFolder)
    _SetBusy(False)
EndFunc

Func _UseIncomingPatch()
    If $g_iQueuedAction <> 0 Then Return
    _SetBusy(True)
    ; Main calls this only after an idle event. _QueueAction locks the current
    ; selection as soon as Windows reports a click, before GUIGetMsg returns
    ; that action. Disabling also cancels a partly pressed button.
    Local $sNextPatch = $g_sIncoming
    GUICtrlSetData($g_idPatch, $sNextPatch)
    $g_sIncoming = ""
    _Log("Selected next patch (not applied): " & $sNextPatch)
    _Status("Patch selected. Choose the target repository, then Apply patch.")
    _SetBusy(False)
    GUICtrlSetState($g_idApply, $GUI_FOCUS)
EndFunc

Func _QueueAction($hWnd, $iMsg, $wParam, $lParam)
    #forceref $iMsg, $lParam
    If $hWnd <> $g_hGUI Then Return $GUI_RUNDEFMSG
    If BitAND(BitShift($wParam, 16), 0xFFFF) <> 0 Then Return $GUI_RUNDEFMSG ; BN_CLICKED only
    Local $id = BitAND($wParam, 0xFFFF)
    If $id <> $g_idApply And $id <> $g_idCheck Then Return $GUI_RUNDEFMSG
    If $g_bBusy Or $g_iQueuedAction <> 0 Then Return 0
    $g_iQueuedAction = $id
    $g_bBusy = True
    $g_sActionPatch = GUICtrlRead($g_idPatch)
    $g_sActionRepo = GUICtrlRead($g_idRepo)
    Return $GUI_RUNDEFMSG
EndFunc

Func _RunOperation($bApply, $sActionPatch = Default, $sActionRepo = Default)
    _SetBusy(True)
    If $sActionPatch <> Default Then GUICtrlSetData($g_idPatch, $sActionPatch)
    If $sActionRepo <> Default Then ControlSetText($g_hGUI, "", $g_idRepo, $sActionRepo)
    $g_bWarnings = False
    $g_sLog = ""
    GUICtrlSetData($g_idLog, "")
    Local $bSuccess = _ProcessPatch($bApply)
    _ReleaseSnapshot()
    If $bSuccess And $bApply Then
        If Not RegWrite($SETTINGS, "CloseAfterSuccess", "REG_DWORD", Number(GUICtrlRead($g_idAutoClose) = $GUI_CHECKED)) Then
            _Warning("The close-after-success preference could not be saved.")
            _Status("Patch applied. Review the warning in the details below.", 0x9B5200)
        EndIf
        If _ShouldAutoClose() Then
            MsgBox($MB_ICONINFORMATION, $APP_TITLE, "Patch applied successfully." & @CRLF & @CRLF & _
                GUICtrlRead($g_idRepo) & @CRLF & @CRLF & "Review and commit the changes in your Git app.", 0, $g_hGUI)
            Exit
        EndIf
    EndIf
    ; Stay busy until the decision to close is complete. Otherwise a second
    ; invocation can be acknowledged in the gap before the success dialog and
    ; then silently discarded when this process exits.
    _SetBusy(False)
EndFunc

Func _ShouldAutoClose()
    Return GUICtrlRead($g_idAutoClose) = $GUI_CHECKED And Not $g_bWarnings And $g_sIncoming = ""
EndFunc

Func _ProcessPatch($bApply, $sHistoryKey = $SETTINGS)
    Local $sPatch = _CleanPath(GUICtrlRead($g_idPatch))
    Local $sRepo = _CleanPath(GUICtrlRead($g_idRepo))
    If Not FileExists($sPatch) Or _IsDirectory($sPatch) Then Return _Fail("Choose an existing patch file.")
    If Not _IsDirectory($sRepo) Then Return _Fail("Choose an existing repository folder.")
    If $g_sGit = "" Or Not FileExists($g_sGit) Then Return _Fail("Git was not found. Use Setup > Locate Git... to select git.exe.")
    _Log("Patch: " & $sPatch & @CRLF & "Selected folder: " & $sRepo & @CRLF & "Git: " & $g_sGit)
    _Status("Checking the repository...")

    Local $sOut = "", $sErr = ""
    If _Git($sRepo, "rev-parse --is-inside-work-tree", $sOut, $sErr) <> 0 Then
        _Log($sOut & $sErr)
        Return _Fail("Git could not open this repository. See the details below.")
    EndIf
    If $sErr <> "" Then _Log($sErr)
    If _TrimLines($sOut) <> "true" Then Return _Fail("Select a Git working tree, not a bare repository or its .git folder.")
    If _Git($sRepo, "rev-parse --show-toplevel", $sOut, $sErr) <> 0 Then
        _Log($sOut & $sErr)
        Return _Fail("Cannot determine the repository root.")
    EndIf
    If $sErr <> "" Then _Log($sErr)
    $sRepo = StringReplace(_TrimLines($sOut), "/", "\")
    If Not _IsDirectory($sRepo) Then Return _Fail("Git returned a repository root that cannot be opened.")
    _RememberRepo($sRepo, $sHistoryKey)
    _Log("Repository root: " & $sRepo)

    ; Ignore inherited Git routing variables, but respect the repository's
    ; normal configuration, attributes and safe.directory checks.
    If _Git($sRepo, "ls-files --unmerged", $sOut, $sErr) <> 0 Then
        _Log($sOut & $sErr)
        Return _Fail("Cannot inspect the repository's conflict state.")
    EndIf
    If $sErr <> "" Then _Log($sErr)
    If $sOut <> "" Then Return _Fail("This repository has unresolved conflicts. Resolve them before applying another patch.")

    ; Snapshot once: check, preview and apply use the exact same bytes even if
    ; a download/editor changes the original patch while the window is open.
    If Not _CreateSnapshot($sPatch) Then Return _Fail("Cannot read the patch or create and protect its temporary copy.")
    If FileGetSize($g_sSnapshot) = 0 Then Return _Fail("The patch file is empty.")
    Local $bSubmodules = _HasSubmoduleHeaders($g_sSnapshot)
    If @error Then Return _Fail("Cannot inspect the temporary patch copy.")
    If $bSubmodules Then Return _Fail("This patch changes Git submodules. Use your Git workflow to apply those changes.")
    Local $sBase = "apply --whitespace=warn "
    Local $sFile = " -- " & _Quote($g_sSnapshot)
    _Status("Checking whether the patch applies...")
    Local $iCheck = _Git($sRepo, $sBase & "--check" & $sFile, $sOut, $sErr)
    _Log("git apply --check" & @CRLF & $sOut & $sErr)
    If $iCheck < 0 Then Return _Fail("Git's patch check could not be completed. No changes made.")
    ; Repeated context can let an already applied patch match a different
    ; block and pass the forward check again. Check both directions before
    ; permitting any write; a reverse check is never an instruction to undo.
    Local $sReverseOut = "", $sReverseErr = "", $bForwardWarnings = $g_bWarnings
    Local $iReverse = _Git($sRepo, "apply --whitespace=nowarn --reverse --check" & $sFile, $sReverseOut, $sReverseErr)
    $g_bWarnings = $bForwardWarnings
    If $iReverse < 0 Then
        _Log($sReverseOut & $sReverseErr)
        Return _Fail("Git's reverse diagnostic could not be completed. No changes made.")
    EndIf
    If $iCheck <> 0 Then
        If $iReverse = 0 Then
            Return _Fail("This patch appears to be already applied (the reverse check succeeds). No changes made.")
        EndIf
        Return _Fail("The patch does not apply to these files. Check the repository and patch version. No changes made.")
    EndIf
    If $iReverse = 0 Then
        Return _Fail("This patch applies in both directions. It may already be applied or have ambiguous context. Inspect the changes before applying manually. No changes made.")
    EndIf

    If _Git($sRepo, $sBase & "--stat --summary" & $sFile, $sOut, $sErr) <> 0 Then
        _Log($sOut & $sErr)
        Return _Fail("Cannot read the patch summary. No changes made.")
    EndIf
    ; Reject patches for which Git reports no applicable file changes.
    If StringStripWS($sOut, 8) = "" Then Return _Fail("The patch contains no applicable working-file changes.")
    _Log("Patch summary:" & @CRLF & $sOut & $sErr)
    If Not $bApply Then
        If $g_bWarnings Then
            _Status("Check passed. No files changed. Review the warnings below.", 0x9B5200)
        Else
            _Status("Check passed. No files changed. Click Apply patch when ready.", 0x176A35)
        EndIf
        Return True
    EndIf

    ; Re-run check for every Apply click; a previous Check-only result is never
    ; cached. Git's apply phase also validates its inputs before writing.
    _Status("Applying patch - please wait...")
    Local $iApply = _Git($sRepo, $sBase & "--verbose" & $sFile, $sOut, $sErr)
    _Log("git apply" & @CRLF & $sOut & $sErr)
    If $iApply = $EXEC_OUTPUT_ERROR Then
        _Warning("Git reported a successful apply, but its output could not be read. Review the working files.")
        _Status("Git reported success. Review the working files; details were unavailable.", 0x9B5200)
        Return True
    EndIf
    If $iApply <> 0 Then
        Return _Fail("Git could not finish applying the patch. Inspect the details and working files before retrying.")
    EndIf
    If $g_bWarnings Then
        _Status("Patch applied. Review the warnings below before committing.", 0x9B5200)
    Else
        _Status("Patch applied successfully. Changes are ready for review and commit.", 0x176A35)
    EndIf
    _Log("SUCCESS: working files updated. Nothing was staged, committed or pushed.")
    Return True
EndFunc

Func _HasSubmoduleHeaders($sPath)
    Local $hFile = FileOpen($sPath, $FO_READ + $FO_UTF8)
    If $hFile = -1 Then Return SetError(1, 0, False)
    Local $sLine, $bInHeaders = False
    While True
        $sLine = FileReadLine($hFile)
        Local $iReadError = @error
        If $iReadError = -1 Then ExitLoop
        If $iReadError Then
            FileClose($hFile)
            Return SetError(1, 0, False)
        EndIf
        If StringLeft($sLine, 11) = "diff --git " Then
            $bInHeaders = True
        ElseIf $bInHeaders Then
            If StringRegExp($sLine, "^(?:index [0-9a-fA-F]+\.\.[0-9a-fA-F]+ |(?:new file|deleted file|old|new) mode )160000$") Then
                FileClose($hFile)
                Return True
            EndIf
            If StringLeft($sLine, 3) = "@@ " Or $sLine = "GIT binary patch" Then $bInHeaders = False
        EndIf
    WEnd
    FileClose($hFile)
    Return SetError(0, 0, False)
EndFunc

Func _Git($sRepo, $sArgs, ByRef $sOut, ByRef $sErr)
    Local $sOptions = "--no-pager -c color.ui=false -c core.quotepath=false -c apply.ignoreWhitespace=no"
    If $sRepo <> "" Then $sOptions &= " -C " & _Quote($sRepo)
    Local $iCode = _Exec($g_sGit, $sOptions & " " & $sArgs, $sOut, $sErr)
    If StringRegExp($sErr, "(?im)^warning:") Then $g_bWarnings = True
    Return $iCode
EndFunc

; Native CreateProcessW retains the exact process handle, including for very
; fast exits. No cmd.exe/PowerShell, shell redirection, or PID exit-code races.
; Separate files avoid pipe deadlocks and preserve stdout for path parsing.
Func _Exec($sExe, $sArgs, ByRef $sOut, ByRef $sErr)
    $sOut = ""
    $sErr = ""
    $g_iCommand += 1
    Local $sStdout = $g_sTempDir & "\stdout-" & $g_iCommand & ".txt"
    Local $sStderr = $g_sTempDir & "\stderr-" & $g_iCommand & ".txt"
    Local $hOut = _OpenInherited($sStdout, 0x40000000, 2)
    Local $hErr = _OpenInherited($sStderr, 0x40000000, 2)
    Local $hIn = _OpenInherited("NUL", 0x80000000, 3)
    If $hOut = -1 Or $hErr = -1 Or $hIn = -1 Then
        _CloseHandle($hOut)
        _CloseHandle($hErr)
        _CloseHandle($hIn)
        _DeletePrivateFile($sStdout)
        _DeletePrivateFile($sStderr)
        $sErr = "Cannot open the temporary command output files."
        Return -1
    EndIf

    Local $sCommand = _Quote($sExe) & " " & $sArgs
    Local $tCmd = DllStructCreate("wchar Text[" & StringLen($sCommand) + 1 & "]")
    DllStructSetData($tCmd, "Text", $sCommand)
    Local $tStart = DllStructCreate($tagSTARTUPINFO)
    Local $tProcess = DllStructCreate($tagPROCESS_INFORMATION)
    DllStructSetData($tStart, "Size", DllStructGetSize($tStart))
    DllStructSetData($tStart, "Flags", 0x100) ; STARTF_USESTDHANDLES
    DllStructSetData($tStart, "StdInput", $hIn)
    DllStructSetData($tStart, "StdOutput", $hOut)
    DllStructSetData($tStart, "StdError", $hErr)
    Local $aCreate = DllCall("kernel32.dll", "bool", "CreateProcessW", "wstr", $sExe, "struct*", $tCmd, _
        "ptr", 0, "ptr", 0, "bool", True, "dword", 0x08000000, "ptr", 0, "wstr", $g_sTempDir, _
        "struct*", $tStart, "struct*", $tProcess) ; CREATE_NO_WINDOW
    Local $iCallError = @error, $iWinError = _LastError()
    _CloseHandle($hOut)
    _CloseHandle($hErr)
    _CloseHandle($hIn)
    If $iCallError Then
        _DeletePrivateFile($sStdout)
        _DeletePrivateFile($sStderr)
        $sErr = "Could not call CreateProcessW. AutoIt error " & $iCallError
        Return -1
    EndIf
    If Not $aCreate[0] Then
        _DeletePrivateFile($sStdout)
        _DeletePrivateFile($sStderr)
        $sErr = "Could not start " & $sExe & ". Windows error " & $iWinError
        Return -1
    EndIf
    Local $hProcess = DllStructGetData($tProcess, "hProcess")
    _CloseHandle(DllStructGetData($tProcess, "hThread"))
    Local $aWait, $iExit = -1
    While True
        $aWait = DllCall("kernel32.dll", "dword", "WaitForSingleObject", "handle", $hProcess, "dword", 0)
        If @error Then ExitLoop
        If $aWait[0] = 0 Then
            Local $aExit = DllCall("kernel32.dll", "bool", "GetExitCodeProcess", "handle", $hProcess, "dword*", 0)
            If Not @error Then
                If $aExit[0] Then $iExit = $aExit[2]
            EndIf
            ExitLoop
        EndIf
        If $aWait[0] <> 258 Then ExitLoop ; WAIT_TIMEOUT
        If $g_hGUI Then
            If GUIGetMsg() = $GUI_EVENT_CLOSE Then _Status("Git is still working. Please wait before closing.")
        EndIf
        Sleep(25)
    WEnd
    _CloseHandle($hProcess)
    $sOut = _ReadUTF8($sStdout)
    Local $iOutError = @error, $iOutTruncated = @extended
    $sErr = _ReadUTF8($sStderr)
    Local $iErrError = @error, $iErrTruncated = @extended
    _DeletePrivateFile($sStdout)
    _DeletePrivateFile($sStderr)
    If $iOutError Or $iErrError Then
        $sErr &= @CRLF & "The command exited with code " & $iExit & ", but its output could not be read completely. Inspect the working files before retrying."
        If $iExit = 0 Then Return $EXEC_OUTPUT_ERROR
    EndIf
    If $iOutTruncated Or $iErrTruncated Then _Warning("Command output was truncated. Review the affected files in your Git app.")
    If $iExit = -1 Then $sErr &= @CRLF & "Could not retrieve Git's exit status. Inspect the working files before retrying."
    Return $iExit
EndFunc

Func _OpenInherited($sPath, $iAccess, $iDisposition)
    Local $tSA = DllStructCreate($tagSECURITY_ATTRIBUTES)
    DllStructSetData($tSA, 1, DllStructGetSize($tSA))
    DllStructSetData($tSA, 3, True)
    Local $aOpen = DllCall("kernel32.dll", "handle", "CreateFileW", "wstr", $sPath, "dword", $iAccess, _
        "dword", 7, "struct*", $tSA, "dword", $iDisposition, "dword", 0x80, "ptr", 0)
    If @error Then Return -1
    If $aOpen[0] = Ptr(-1) Then Return -1
    Return $aOpen[0]
EndFunc

Func _CloseHandle($hHandle)
    If $hHandle = 0 Or $hHandle = -1 Then Return
    DllCall("kernel32.dll", "bool", "CloseHandle", "handle", $hHandle)
EndFunc

Func _LastError()
    Local $aError = DllCall("kernel32.dll", "dword", "GetLastError")
    If @error Then Return -1
    Return $aError[0]
EndFunc

Func _ReadUTF8($sPath)
    Local $hFile = FileOpen($sPath, $FO_BINARY)
    If $hFile = -1 Then Return SetError(1, 0, "")
    Local $bData = FileRead($hFile, $MAX_LOG)
    Local $iReadError = @error
    FileClose($hFile)
    If $iReadError <> 0 And $iReadError <> -1 Then Return SetError(1, 0, "")
    Local $iSize = FileGetSize($sPath)
    If @error Then Return SetError(1, 0, "")
    Local $iTruncated = Number($iSize > $MAX_LOG)
    If $iTruncated Then _TrimUTF8Tail($bData)
    Local $sText = ""
    If BinaryLen($bData) Then
        $sText = BinaryToString($bData, 4)
        If @error Then Return SetError(2, 0, "")
    EndIf
    If $iTruncated Then $sText &= @CRLF & "[Output truncated at 4 MB.]"
    Return SetError(0, $iTruncated, $sText)
EndFunc

Func _TrimUTF8Tail(ByRef $bData)
    ; The byte limit may split the last UTF-8 code point. Drop only that
    ; incomplete suffix; never discard an otherwise valid captured prefix.
    Local $iLength = BinaryLen($bData), $iStart = BinaryLen($bData)
    If Not $iLength Then Return
    Local $iByte = Dec(Hex(BinaryMid($bData, $iStart, 1)))
    While $iStart > 1 And BitAND($iByte, 0xC0) = 0x80 And $iLength - $iStart < 3
        $iStart -= 1
        $iByte = Dec(Hex(BinaryMid($bData, $iStart, 1)))
    WEnd
    Local $iNeeded = 1
    If $iByte >= 0xC2 And $iByte <= 0xDF Then $iNeeded = 2
    If $iByte >= 0xE0 And $iByte <= 0xEF Then $iNeeded = 3
    If $iByte >= 0xF0 And $iByte <= 0xF4 Then $iNeeded = 4
    If $iLength - $iStart + 1 < $iNeeded Then $bData = BinaryMid($bData, 1, $iStart - 1)
EndFunc

; Windows CRT command-line quoting, including trailing backslashes and quotes.
Func _Quote($sValue)
    Local $sResult = '"', $iSlashes = 0, $sChar
    For $i = 1 To StringLen($sValue)
        $sChar = StringMid($sValue, $i, 1)
        If $sChar = '\' Then
            $iSlashes += 1
        ElseIf $sChar = '"' Then
            $sResult &= _StringRepeat('\', $iSlashes * 2 + 1) & '"'
            $iSlashes = 0
        Else
            $sResult &= _StringRepeat('\', $iSlashes) & $sChar
            $iSlashes = 0
        EndIf
    Next
    Return $sResult & _StringRepeat('\', $iSlashes * 2) & '"'
EndFunc

Func _CleanPath($sPath)
    $sPath = StringStripWS($sPath, 3)
    If StringLeft($sPath, 1) = '"' And StringRight($sPath, 1) = '"' Then $sPath = StringTrimRight(StringTrimLeft($sPath, 1), 1)
    If $sPath = "" Then Return ""
    Return _PathFull($sPath, @WorkingDir)
EndFunc

; Compare directory names without changing the path passed to Windows/Git.
; Drive and share roots remain distinct; a trailing separator is immaterial.
Func _DirectoryKey($sPath)
    Return StringLower(StringRegExpReplace(StringReplace($sPath, "/", "\"), "[\\]+$", ""))
EndFunc

Func _TrimLines($sText)
    Return StringRegExpReplace($sText, "[\r\n]+$", "")
EndFunc

Func _IsDirectory($sPath)
    Return $sPath <> "" And StringInStr(FileGetAttrib($sPath), "D") <> 0
EndFunc

Func _CleanGitEnvironment()
    ; These variables can redirect Git away from the selected repository.
    Local $aNames = StringSplit("GIT_DIR|GIT_WORK_TREE|GIT_INDEX_FILE|GIT_COMMON_DIR|GIT_OBJECT_DIRECTORY|GIT_ALTERNATE_OBJECT_DIRECTORIES|GIT_NAMESPACE|GIT_PREFIX|GIT_CEILING_DIRECTORIES|GIT_CONFIG|GIT_CONFIG_COUNT|GIT_CONFIG_PARAMETERS|GIT_SHALLOW_FILE", "|", 2)
    For $sName In $aNames
        EnvSet($sName)
    Next
    EnvSet("GIT_TERMINAL_PROMPT", "0")
    EnvSet("GIT_OPTIONAL_LOCKS", "0")
    EnvSet("LC_ALL", "C.UTF-8")
EndFunc

Func _FindGit()
    Local $sSaved = RegRead($SETTINGS, "GitExe")
    If FileExists($sSaved) And Not _IsDirectory($sSaved) Then Return $sSaved
    Local $aRoots[7] = [RegRead("HKCU\Software\GitForWindows", "InstallPath"), _ReadGitMachine(), _
        EnvGet("ProgramW6432") & "\Git", @ProgramFilesDir & "\Git", EnvGet("ProgramFiles(x86)") & "\Git", _
        @LocalAppDataDir & "\Programs\Git", @LocalAppDataDir & "\Git"]
    For $sRoot In $aRoots
        If $sRoot = "" Then ContinueLoop
        If FileExists($sRoot & "\cmd\git.exe") Then Return $sRoot & "\cmd\git.exe"
        If FileExists($sRoot & "\bin\git.exe") Then Return $sRoot & "\bin\git.exe"
    Next
    Local $aPath = StringSplit(EnvGet("PATH"), ";", 2), $sCandidate
    For $sEntry In $aPath
        $sEntry = StringReplace(StringStripWS($sEntry, 3), '"', "")
        ; Do not search the current directory or relative PATH entries.
        If Not StringRegExp($sEntry, "^(?:[A-Za-z]:[\\/]|\\\\)") Then ContinueLoop
        $sCandidate = $sEntry & "\git.exe"
        If FileExists($sCandidate) And Not _IsDirectory($sCandidate) Then Return $sCandidate
    Next
    Return ""
EndFunc

Func _ReadGitMachine()
    Local $sPath = ""
    If @OSArch = "X64" Then $sPath = RegRead("HKLM64\Software\GitForWindows", "InstallPath")
    If $sPath = "" Then $sPath = RegRead("HKLM\Software\GitForWindows", "InstallPath")
    Return $sPath
EndFunc

Func _ChooseGit()
    _SetBusy(True)
    Local $sFile = FileOpenDialog("Select Git for Windows: usually C:\Program Files\Git\cmd\git.exe", "", "Git executable (git.exe)", $FD_FILEMUSTEXIST, "", $g_hGUI)
    If @error Then
        _SetBusy(False)
        Return
    EndIf
    Local $sOld = $g_sGit, $sOut = "", $sErr = ""
    $g_sGit = $sFile
    Local $iCode = _Git("", "--version", $sOut, $sErr)
    If $iCode <> 0 Or StringLeft($sOut, 12) <> "git version " Then
        $g_sGit = $sOld
        _Log($sOut & $sErr)
        _Fail("That executable did not report a Git version.")
        _SetBusy(False)
        Return
    EndIf
    If Not RegWrite($SETTINGS, "GitExe", "REG_SZ", $g_sGit) Then
        _Status("Git selected, but its path could not be saved.", 0x9B5200)
    Else
        _Status("Using " & _TrimLines($sOut), 0x176A35)
    EndIf
    _SetBusy(False)
EndFunc

Func _LoadRecent($sKey = $SETTINGS)
    ReDim $g_aRecent[0]
    Local $sValue = RegRead($sKey, "RecentRepos")
    If @error Or $sValue = "" Then Return
    Local $aPaths = StringSplit($sValue, @LF, 2)
    For $sPath In $aPaths
        If $sPath = "" Then ContinueLoop
        If UBound($g_aRecent) >= $MAX_RECENT Then ExitLoop
        ReDim $g_aRecent[UBound($g_aRecent) + 1]
        $g_aRecent[UBound($g_aRecent) - 1] = $sPath
    Next
EndFunc

Func _RememberRepo($sRepo, $sKey = $SETTINGS)
    _LoadRecent($sKey)
    _PromoteRecent($g_aRecent, $sRepo)
    _SaveRecent($sKey)
    _RefreshRecent($sRepo)
EndFunc

Func _PromoteRecent(ByRef $aRecent, $sRepo)
    Local $aNew[1] = [$sRepo]
    For $sOld In $aRecent
        If _DirectoryKey($sOld) = _DirectoryKey($sRepo) Then ContinueLoop
        If UBound($aNew) >= $MAX_RECENT Then ExitLoop
        ReDim $aNew[UBound($aNew) + 1]
        $aNew[UBound($aNew) - 1] = $sOld
    Next
    $aRecent = $aNew
EndFunc

Func _SaveRecent($sKey = $SETTINGS)
    Local $sValue = ""
    For $sPath In $g_aRecent
        If $sValue <> "" Then $sValue &= @LF
        $sValue &= $sPath
    Next
    If Not RegWrite($sKey, "RecentRepos", "REG_MULTI_SZ", $sValue) Then
        _Warning("Repository history could not be saved.")
        Return False
    EndIf
    Return True
EndFunc

Func _RefreshRecent($sSelected)
    _GUICtrlComboBox_ResetContent($g_idRepo)
    For $sPath In $g_aRecent
        _GUICtrlComboBox_AddString($g_idRepo, $sPath)
    Next
    ControlSetText($g_hGUI, "", $g_idRepo, $sSelected)
EndFunc

Func _ForgetRepo()
    Local $sRemove = _CleanPath(GUICtrlRead($g_idRepo))
    _LoadRecent()
    _RemoveRecent($g_aRecent, $sRemove)
    If Not _SaveRecent() Then
        _LoadRecent()
        _RefreshRecent($sRemove)
        _Fail("History could not be saved. The stored path was retained.")
        Return
    EndIf
    Local $sFirst = ""
    If UBound($g_aRecent) Then $sFirst = $g_aRecent[0]
    _RefreshRecent($sFirst)
    _Status("Path removed from history. Repository files were not changed.")
EndFunc

Func _RemoveRecent(ByRef $aRecent, $sRemove)
    Local $aNew[0]
    For $sPath In $aRecent
        If _DirectoryKey($sPath) = _DirectoryKey($sRemove) Then ContinueLoop
        ReDim $aNew[UBound($aNew) + 1]
        $aNew[UBound($aNew) - 1] = $sPath
    Next
    $aRecent = $aNew
EndFunc

Func _InstallMenu($sAppDir = $APP_DIR, $sMenuKey = $MENU_KEY, $sLink = Default)
    If $sLink = Default Then $sLink = @ProgramsDir & "\Patch to Repo"
    If Not _IsDirectory($sAppDir) Then
        If Not DirCreate($sAppDir) Then Return _SetupError("Cannot create " & $sAppDir)
    EndIf
    Local $sTarget, $sCommand, $sShortcutExe, $sShortcutArgs = ""
    If @Compiled Then
        $sTarget = $sAppDir & "\PatchToRepo.exe"
        $sCommand = _Quote($sTarget)
        $sShortcutExe = $sTarget
    Else
        $sTarget = $sAppDir & "\PatchToRepo.au3"
        $sCommand = _Quote(@AutoItExe) & " " & _Quote($sTarget)
        $sShortcutExe = @AutoItExe
        $sShortcutArgs = _Quote($sTarget)
    EndIf
    If StringLower(@ScriptFullPath) <> StringLower($sTarget) Then
        If Not _InstallFile(@ScriptFullPath, $sTarget) Then Return _SetupError("Cannot update the installed helper at " & $sTarget & @CRLF & "Close other instances, then retry.")
    EndIf
    ; Compiled builds use their embedded icon; source installs keep a stable ICO.
    Local $sIconPath = $sTarget
    If Not @Compiled Then
        Local $sSourceIcon = @ScriptDir & "\assets\PatchToRepo.ico"
        $sIconPath = $sAppDir & "\assets\PatchToRepo.ico"
        If FileExists($sSourceIcon) And Not _IsDirectory($sSourceIcon) Then
            If Not _IsDirectory($sAppDir & "\assets") Then
                If Not DirCreate($sAppDir & "\assets") Then Return _SetupError("Cannot create the installed icon folder.")
            EndIf
            If StringLower($sSourceIcon) <> StringLower($sIconPath) Then
                If Not _InstallFile($sSourceIcon, $sIconPath) Then Return _SetupError("Cannot update the installed icon at " & $sIconPath)
            EndIf
        EndIf
        ; A standalone source copy without its asset remains usable.
        If Not FileExists($sIconPath) Or _IsDirectory($sIconPath) Then $sIconPath = @AutoItExe
    EndIf
    Local $bOK = True
    If Not RegWrite($sMenuKey, "MUIVerb", "REG_SZ", "Apply patch to repository...") Then $bOK = False
    If Not RegWrite($sMenuKey, "Icon", "REG_SZ", _Quote($sIconPath) & ",0") Then $bOK = False
    If Not RegWrite($sMenuKey, "MultiSelectModel", "REG_SZ", "Single") Then $bOK = False
    If Not RegWrite($sMenuKey & "\command", "", "REG_SZ", $sCommand & ' --apply "%1"') Then $bOK = False
    _NotifyShell()
    If Not $bOK Then Return _SetupError("The context-menu registration could not be completed. Try Setup > Install / repair context menu.")
    If Not _IsDirectory($sLink) Then
        If Not DirCreate($sLink) Then Return _SetupError("The context menu was installed, but the Start menu folder could not be created.")
    EndIf
    If Not FileCreateShortcut($sShortcutExe, $sLink & "\Patch to Repo.lnk", $sAppDir, $sShortcutArgs, "Apply a patch to a Git repository", $sIconPath) Then
        Return _SetupError("The context menu was installed, but the Start menu shortcut could not be created.")
    EndIf
    If Not FileCreateShortcut($sShortcutExe, $sLink & "\Remove context menu.lnk", $sAppDir, $sShortcutArgs & " --uninstall", "Remove the Patch to Repo menu and shortcuts", $sIconPath) Then
        Return _SetupError("The context menu was installed, but the removal shortcut could not be created.")
    EndIf
    Return True
EndFunc

; Stage in the destination directory and rename only after a complete copy.
; A failed copy cannot truncate an existing installed script or executable.
Func _InstallFile($sSource, $sTarget)
    Local $sStage = $sTarget & ".update-" & @AutoItPID
    If FileExists($sStage) Then Return False
    If Not FileCopy($sSource, $sStage, $FC_NOOVERWRITE) Then
        _DeletePrivateFile($sStage)
        Return False
    EndIf
    If Not _MakeWritable($sStage) Then
        _DeletePrivateFile($sStage)
        Return False
    EndIf
    Local $iOldAttrs = -1
    If FileExists($sTarget) Then
        Local $aAttrs = DllCall("kernel32.dll", "dword", "GetFileAttributesW", "wstr", $sTarget)
        If Not @error Then $iOldAttrs = $aAttrs[0]
        If Not _MakeWritable($sTarget) Then
            _DeletePrivateFile($sStage)
            Return False
        EndIf
    EndIf
    Local $aMove = DllCall("kernel32.dll", "bool", "MoveFileExW", "wstr", $sStage, "wstr", $sTarget, "dword", 9)
    Local $iMoveError = @error, $bMoved = False ; MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
    If Not $iMoveError Then $bMoved = $aMove[0] <> 0
    If Not $bMoved Then
        If $iOldAttrs <> -1 Then DllCall("kernel32.dll", "bool", "SetFileAttributesW", "wstr", $sTarget, "dword", $iOldAttrs)
        _DeletePrivateFile($sStage)
    EndIf
    Return $bMoved
EndFunc

; Only call this for the helper's own installed or temporary files.
Func _MakeWritable($sPath)
    Local $aAttrs = DllCall("kernel32.dll", "dword", "GetFileAttributesW", "wstr", $sPath)
    If @error Then Return False
    If $aAttrs[0] = 0xFFFFFFFF Or BitAND($aAttrs[0], 0x10) Then Return False
    Local $iAttrs = BitAND($aAttrs[0], BitNOT(7)) ; clear READONLY, HIDDEN, SYSTEM
    If Not $iAttrs Then $iAttrs = 0x80
    Local $aSet = DllCall("kernel32.dll", "bool", "SetFileAttributesW", "wstr", $sPath, "dword", $iAttrs)
    If @error Then Return False
    Return $aSet[0] <> 0
EndFunc

Func _DeletePrivateFile($sPath)
    If Not FileExists($sPath) Then Return True
    If Not _MakeWritable($sPath) Then Return False
    Return FileDelete($sPath) <> 0
EndFunc

Func _CreateSnapshot($sSource)
    _ReleaseSnapshot()
    $g_iOperation += 1
    $g_sSnapshot = $g_sTempDir & "\selected-" & $g_iOperation & ".patch"
    If Not FileCopy($sSource, $g_sSnapshot, $FC_NOOVERWRITE) Then Return False
    If Not _MakeWritable($g_sSnapshot) Then Return False
    ; Lock the checked bytes against writes, deletion and replacement. Git can
    ; open another read handle while check/summary/application use the copy.
    Local $aOpen = DllCall("kernel32.dll", "handle", "CreateFileW", "wstr", $g_sSnapshot, "dword", 0x80000000, _
        "dword", 1, "ptr", 0, "dword", 3, "dword", 0x80, "ptr", 0)
    If @error Then Return False
    If $aOpen[0] = Ptr(-1) Then Return False
    $g_hSnapshot = $aOpen[0]
    Return True
EndFunc

Func _ReleaseSnapshot()
    _CloseHandle($g_hSnapshot)
    $g_hSnapshot = 0
    If $g_sSnapshot <> "" Then _DeletePrivateFile($g_sSnapshot)
    $g_sSnapshot = ""
EndFunc

Func _RemoveMenu($sMenuKey = $MENU_KEY, $sLink = Default)
    If $sLink = Default Then $sLink = @ProgramsDir & "\Patch to Repo"
    ; RegDelete returns 0 for absent, 1 for success, and 2 for failure.
    Local $iResult = RegDelete($sMenuKey)
    If $iResult = 2 Then Return _SetupError("Cannot remove the Patch to Repo context-menu entry.")
    Local $bOK = _DeleteShortcut($sLink & "\Patch to Repo.lnk")
    If Not _DeleteShortcut($sLink & "\Remove context menu.lnk") Then $bOK = False
    DirRemove($sLink) ; non-recursive: preserve unrelated files
    _NotifyShell()
    If Not $bOK Then
        Return _SetupError("The context menu was removed, but a Start menu shortcut could not be deleted.")
    EndIf
    Return True
EndFunc

Func _DeleteShortcut($sPath)
    ; AutoIt's FileDelete treats a directory argument as a file mask. The
    ; native API only deletes a file and cannot erase a directory's contents.
    Local $aDelete = DllCall("kernel32.dll", "bool", "DeleteFileW", "wstr", $sPath)
    If @error Then Return False
    If $aDelete[0] Then Return True
    Local $iError = _LastError()
    Return $iError = 2 Or $iError = 3 ; FILE_NOT_FOUND / PATH_NOT_FOUND
EndFunc

Func _NotifyShell()
    DllCall("shell32.dll", "none", "SHChangeNotify", "long", 0x08000000, "uint", 0, "ptr", 0, "ptr", 0)
EndFunc

Func _SetupError($sText)
    If $g_bTesting Then
        ConsoleWrite("EXPECTED/TEST SETUP ERROR: " & $sText & @CRLF)
        Return False
    EndIf
    Local $bWasBusy = $g_bBusy
    $g_bBusy = True
    MsgBox($MB_ICONERROR, $APP_TITLE, $sText, 0, $g_hGUI)
    $g_bBusy = $bWasBusy
    Return False
EndFunc

Func _SetBusy($bBusy)
    $g_bBusy = $bBusy
    Local $aIDs[16] = [$g_idPatch, $g_idRepo, $g_idBrowsePatch, $g_idBrowseRepo, $g_idForget, $g_idCheck, $g_idApply, _
        $g_idClose, $g_idAutoClose, $g_idGit, $g_idInstall, $g_idUninstall, $g_idCopy, $g_idFolder, _
        $g_idInstallButton, $g_idUninstallButton]
    Local $iState = $GUI_ENABLE
    If $bBusy Then $iState = $GUI_DISABLE
    For $id In $aIDs
        GUICtrlSetState($id, $iState)
    Next
EndFunc

Func _Status($sText, $iColor = 0x334155)
    If Not $g_hGUI Then Return
    GUICtrlSetData($g_idStatus, $sText)
    GUICtrlSetColor($g_idStatus, $iColor)
EndFunc

Func _Fail($sText)
    _Status($sText, 0xAF2525)
    _Log($sText)
    Return False
EndFunc

Func _Warning($sText)
    $g_bWarnings = True
    _Log("WARNING: " & $sText)
EndFunc

Func _Log($sText)
    If $sText = "" Then Return
    $sText = StringReplace(StringStripCR($sText), @LF, @CRLF)
    $g_sLog &= $sText & @CRLF & @CRLF
    If StringLen($g_sLog) > $MAX_LOG Then $g_sLog = StringRight($g_sLog, $MAX_LOG)
    If $g_idLog Then
        GUICtrlSetData($g_idLog, $g_sLog)
        _GUICtrlEdit_SetSel($g_idLog, -1, -1)
        _GUICtrlEdit_Scroll($g_idLog, $SB_SCROLLCARET)
    EndIf
EndFunc

Func _ForwardPatch($hWindow, $sPatch)
    Local $tText = DllStructCreate("wchar Text[" & StringLen($sPatch) + 1 & "]")
    DllStructSetData($tText, "Text", $sPatch)
    Local $tCopy = DllStructCreate("ulong_ptr Tag;dword Bytes;ptr Data")
    DllStructSetData($tCopy, "Tag", 0x50545231)
    DllStructSetData($tCopy, "Bytes", DllStructGetSize($tText))
    DllStructSetData($tCopy, "Data", DllStructGetPtr($tText))
    Local $aSend = DllCall("user32.dll", "lresult", "SendMessageTimeoutW", "hwnd", $hWindow, "uint", $WM_COPYDATA, _
        "wparam", 0, "struct*", $tCopy, "uint", 2, "uint", 1500, "ulong_ptr*", 0)
    If @error Then Return False
    Return $aSend[0] <> 0 And $aSend[7] = 1
EndFunc

Func _FindInstanceWindow($iPID = 0, $sProperty = $INSTANCE_PROPERTY)
    ; Window titles also occur on message boxes and Explorer folders. Use an
    ; application property to locate the actual picker instead of its title.
    Local $aWindows = WinList("[CLASS:AutoIt v3 GUI]")
    For $i = 1 To $aWindows[0][0]
        Local $aProp = DllCall("user32.dll", "handle", "GetPropW", "hwnd", $aWindows[$i][1], "wstr", $sProperty)
        If @error Then ContinueLoop
        If $aProp[0] = 0 Then ContinueLoop
        Local $iOwner = WinGetProcess($aWindows[$i][1])
        If $iPID <> 0 And $iOwner <> $iPID Then ContinueLoop
        If Number($aProp[0]) = $iOwner Then Return $aWindows[$i][1]
    Next
    Return 0
EndFunc

Func _ReceivePatch($hWnd, $iMsg, $wParam, $lParam)
    #forceref $hWnd, $iMsg, $wParam
    If $g_bBusy Or Not $lParam Or $g_sIncoming <> "" Then Return 0
    Local $tCopy = DllStructCreate("ulong_ptr Tag;dword Bytes;ptr Data", $lParam)
    If DllStructGetData($tCopy, "Tag") <> 0x50545231 Then Return 0
    Local $iSize = DllStructGetData($tCopy, "Bytes")
    If $iSize < 4 Or $iSize > 65536 Or Mod($iSize, 2) <> 0 Then Return 0
    If Not DllStructGetData($tCopy, "Data") Then Return 0
    Local $tText = DllStructCreate("wchar Text[" & $iSize / 2 & "]", DllStructGetData($tCopy, "Data"))
    $g_sIncoming = DllStructGetData($tText, "Text")
    Return 1
EndFunc

Func _MakeTempDir()
    For $i = 1 To 10
        $g_sTempDir = @TempDir & "\PatchToRepo-" & @AutoItPID & "-" & Hex(Random(0, 0x7FFFFFFF, 1), 8)
        ; CreateDirectory is exclusive; unlike DirCreate it fails if it exists.
        Local $aCreate = DllCall("kernel32.dll", "bool", "CreateDirectoryW", "wstr", $g_sTempDir, "ptr", 0)
        If Not @error Then
            If $aCreate[0] Then Return True
        EndIf
    Next
    $g_sTempDir = ""
    Return False
EndFunc

Func _Cleanup()
    $g_bBusy = True
    _ReleaseSnapshot()
    _DestroyGUI()
    If $g_sTestKey <> "" Then RegDelete($g_sTestKey)
    If $g_sTempDir <> "" Then DirRemove($g_sTempDir, $DIR_REMOVE)
EndFunc

Func _DestroyGUI()
    If Not $g_hGUI Then Return
    GUIRegisterMsg($WM_COPYDATA, "")
    GUIRegisterMsg($WM_COMMAND, "")
    DllCall("user32.dll", "handle", "RemovePropW", "hwnd", $g_hGUI, "wstr", $INSTANCE_PROPERTY)
    GUIDelete($g_hGUI)
    $g_hGUI = 0
EndFunc

Func _SelfTest()
    $g_bTesting = True
    If Not _MakeTempDir() Then Return 99
    OnAutoItExitRegister("_Cleanup")
    $g_sTestKey = $g_sHive & "\Software\PatchToRepoSelfTest-" & @AutoItPID & "-" & Hex(Random(0, 0x7FFFFFFF, 1), 8)
    _CleanGitEnvironment()
    EnvSet("GIT_CONFIG_NOSYSTEM", "1")
    EnvSet("GIT_CONFIG_GLOBAL", "NUL")
    _Assert(_Quote("") = '""', "Quote empty argument")
    _Assert(_Quote("C:\repo name\") = '"C:\repo name\\"', "Quote trailing backslash")
    _Assert(_Quote('x"y') = '"x\"y"', "Quote embedded quotation mark")
    _Assert(_Quote("C:\x & y%z!\p.patch") = '"C:\x & y%z!\p.patch"', "Keep shell metacharacters literal")
    _Assert(_DirectoryKey("C:\repo\") = _DirectoryKey("c:/repo"), "Normalize recent-path separators")
    _Assert(_DirectoryKey("C:\") <> _DirectoryKey("D:\"), "Keep drive roots distinct")
    _Assert(_DirectoryKey("\\server\share\") <> _DirectoryKey("\\server\other\"), "Keep UNC share roots distinct")

    Local $aRecent[0]
    For $i = 1 To 25
        _PromoteRecent($aRecent, "C:\repo" & $i)
    Next
    _Assert(UBound($aRecent) = $MAX_RECENT And $aRecent[0] = "C:\repo25", "Bound MRU history and order")
    _PromoteRecent($aRecent, "C:\repo20\")
    _Assert(UBound($aRecent) = $MAX_RECENT And $aRecent[0] = "C:\repo20\", "Deduplicate trailing slash in MRU")
    _RemoveRecent($aRecent, "c:/repo20")
    _Assert(UBound($aRecent) = $MAX_RECENT - 1, "Forget a path with alternate separators")
    $g_aRecent = $aRecent
    _Assert(_SaveRecent($g_sTestKey & "\History"), "Save isolated history")
    _LoadRecent($g_sTestKey & "\History")
    _Assert(UBound($g_aRecent) = UBound($aRecent), "Read isolated history")

    Local $sOut = "", $sErr = "", $iCode
    ; Fixed shell commands occur only in this explicitly requested test mode.
    For $i = 1 To 20
        $iCode = _Exec(@ComSpec, "/d /c exit 7", $sOut, $sErr)
        _Assert($iCode = 7, "Fast child exit " & $i)
    Next
    $iCode = _Exec(@ComSpec, "/d /c echo " & _StringRepeat("x", 500), $sOut, $sErr)
    _Assert($iCode = 0 And _TrimLines($sOut) = _StringRepeat("x", 500), "Command line beyond 260 characters")
    $iCode = _Exec(@ComSpec, "/d /c echo error 1>&2", $sOut, $sErr)
    _Assert($iCode = 0 And $sOut = "" And StringInStr($sErr, "error") > 0, "Separate stdout and stderr")
    $iCode = _Exec($g_sTempDir & "\missing.exe", "", $sOut, $sErr)
    _Assert($iCode = -1 And $sErr <> "", "Report launch failure")
    Local $sUnreadable = _ReadUTF8($g_sTempDir & "\missing-output.txt")
    Local $iReadFailure = @error
    _Assert($iReadFailure <> 0 And $sUnreadable = "", "Report output read failure without inventing Git output")
    Local $sEmptyOutput = $g_sTempDir & "\empty-output.txt"
    _TestWrite($sEmptyOutput, "")
    $sUnreadable = _ReadUTF8($sEmptyOutput)
    $iReadFailure = @error
    _Assert($iReadFailure = 0 And $sUnreadable = "", "Accept genuinely empty command output")
    Local $sLargeOutput = $g_sTempDir & "\large-output.txt"
    _TestWrite($sLargeOutput, _StringRepeat("x", $MAX_LOG - 1) & ChrW(0xE4))
    $sUnreadable = _ReadUTF8($sLargeOutput)
    $iReadFailure = @error
    Local $iWasTruncated = @extended
    _Assert($iReadFailure = 0 And $iWasTruncated = 1 And StringLeft($sUnreadable, $MAX_LOG - 1) = _StringRepeat("x", $MAX_LOG - 1), "Preserve UTF-8 prefix when output limit splits a character")
    If Not @Compiled Then
        Local $sFaultProbe = $g_sTempDir & "\fatal-probe.au3"
        _TestWrite($sFaultProbe, '#NoTrayIcon' & @CRLF & 'Opt("SetExitCode", 1)' & @CRLF & 'FileWrite(@ScriptDir & "\fault-started.txt", "started")' & @CRLF & _
            'Local $a[1], $i = 5' & @CRLF & 'ConsoleWrite($a[$i])' & @CRLF)
        $iCode = _Exec(@AutoItExe, "/ErrorStdOut " & _Quote($sFaultProbe), $sOut, $sErr)
        _Assert($iCode > 0 And FileRead($g_sTempDir & "\fault-started.txt") = "started", "Runtime failures return a nonzero exit status")
    EndIf

    Local $sOriginal = $g_sTempDir & "\readonly " & ChrW(0xE4) & " & 100% !.patch"
    _TestWrite($sOriginal, "snapshot bytes" & @LF)
    _Assert(_TestSetAttributes($sOriginal, 1), "Create read-only source fixture")
    _Assert(_CreateSnapshot($sOriginal), "Snapshot a read-only source")
    _Assert(FileRead($g_sSnapshot) = "snapshot bytes" & @LF, "Read locked snapshot")
    _Assert(Not FileDelete($g_sSnapshot), "Snapshot cannot be deleted while checked bytes are locked")
    Local $sOldSnapshot = $g_sSnapshot
    _ReleaseSnapshot()
    _Assert(Not FileExists($sOldSnapshot), "Release removes read-only-derived snapshot")
    _Assert(_CreateSnapshot($sOriginal), "Create a second snapshot in the same session")
    _ReleaseSnapshot()
    _Assert(StringInStr(FileGetAttrib($sOriginal), "R") > 0, "Source attributes remain intact")
    _MakeWritable($sOriginal)

    Local $sStageSource = $g_sTempDir & "\new.au3", $sStageTarget = $g_sTempDir & "\installed.au3"
    _TestWrite($sStageSource, "new version")
    _TestWrite($sStageTarget, "old version")
    _TestSetAttributes($sStageSource, 1)
    _TestSetAttributes($sStageTarget, 1)
    _Assert(_InstallFile($sStageSource, $sStageTarget), "Update from and over read-only files")
    _Assert(FileRead($sStageTarget) = "new version", "Installed bytes match completed copy")
    _Assert(Not StringInStr(FileGetAttrib($sStageTarget), "R"), "Installed copy stays updatable")
    _Assert(StringInStr(FileGetAttrib($sStageSource), "R") > 0, "Update preserves source attributes")
    _MakeWritable($sStageSource)
    _Assert(Not _InstallFile($g_sTempDir & "\absent.au3", $sStageTarget), "Failed source copy is reported")
    _Assert(FileRead($sStageTarget) = "new version", "Failed update preserves installed bytes")

    ; A directory with a shortcut-like name must never lose its contents.
    Local $sFakeShortcut = $g_sTempDir & "\unexpected.lnk"
    DirCreate($sFakeShortcut)
    _TestWrite($sFakeShortcut & "\keep.txt", "keep")
    _Assert(Not _DeleteShortcut($sFakeShortcut), "Refuse directory in place of shortcut")
    _Assert(FileRead($sFakeShortcut & "\keep.txt") = "keep", "Unexpected shortcut directory contents survive")

    Local $sTestApp = $g_sTempDir & "\installed app", $sTestLinks = $g_sTempDir & "\shortcuts"
    Local $sTestMenu = $g_sTestKey & "\Menu"
    _Assert(_InstallMenu($sTestApp, $sTestMenu, $sTestLinks), "Install in isolated paths and registry key")
    _Assert(RegRead($sTestMenu, "MultiSelectModel") = "Single", "Register single-selection verb")
    _Assert(StringRight(RegRead($sTestMenu & "\command", ""), 13) = ' --apply "%1"', "Quote Explorer patch argument")
    _Assert(FileExists($sTestLinks & "\Patch to Repo.lnk"), "Create launcher shortcut")
    _Assert(FileExists($sTestLinks & "\Remove context menu.lnk"), "Create removal shortcut")
    _Assert(_RemoveMenu($sTestMenu, $sTestLinks), "Remove isolated menu and shortcuts")
    _Assert(Not FileExists($sTestLinks & "\Patch to Repo.lnk"), "Remove launcher shortcut")
    ; Use a file where a shortcut directory is required to force setup failure.
    Local $sBlockedLinks = $g_sTempDir & "\not-a-directory"
    _TestWrite($sBlockedLinks, "keep")
    _Assert(Not _InstallMenu($sTestApp, $sTestMenu, $sBlockedLinks), "Setup reports shortcut-folder failure")
    _Assert(FileRead($sBlockedLinks) = "keep", "Failed shortcut creation preserves unrelated file")
    _RemoveMenu($sTestMenu, $sTestLinks)

    _CreateGUI("", False, False)
    _Assert(_ControlsValid(), "Create complete hidden picker")
    Local $idSavedApply = $g_idApply
    $g_idApply = 0
    _Assert(Not _ControlsValid(), "Refuse an uninitialized Apply control")
    $g_idApply = $idSavedApply
    Local $sTestProperty = $INSTANCE_PROPERTY & ".Test." & @AutoItPID
    DllCall("user32.dll", "bool", "SetPropW", "hwnd", $g_hGUI, "wstr", $sTestProperty, "handle", @AutoItPID)
    Local $hOther = GUICreate($APP_TITLE, 120, 60)
    _Assert(_FindInstanceWindow(@AutoItPID, $sTestProperty) = $g_hGUI, "Find marked picker despite title collision")
    GUIDelete($hOther)
    GUISwitch($g_hGUI)
    DllCall("user32.dll", "handle", "RemovePropW", "hwnd", $g_hGUI, "wstr", $sTestProperty)
    $g_bBusy = False
    _Assert(_ForwardPatch($g_hGUI, $sOriginal), "Pass a patch to an idle picker")
    _Assert($g_sIncoming = $sOriginal, "Preserve Unicode path in IPC")
    GUICtrlSetState($g_idAutoClose, $GUI_CHECKED)
    $g_bWarnings = False
    _Assert(Not _ShouldAutoClose(), "Keep an acknowledged pending handoff through operation completion")
    GUICtrlSetData($g_idPatch, "prior.patch")
    ControlSetText($g_hGUI, "", $g_idRepo, $g_sTempDir)
    DllCall("user32.dll", "lresult", "SendMessageW", "hwnd", $g_hGUI, "uint", $WM_COMMAND, "wparam", $g_idCheck, "lparam", GUICtrlGetHandle($g_idCheck))
    _Assert($g_iQueuedAction = $g_idCheck And $g_bBusy, "Lock the current selection before queued Check dispatch")
    GUICtrlSetData($g_idPatch, "later.patch")
    _Assert($g_sActionPatch = "prior.patch" And $g_sActionRepo = $g_sTempDir, "Capture the patch and repository belonging to the click")
    _UseIncomingPatch()
    _Assert($g_sIncoming = $sOriginal, "Do not replace the selection while an earlier action is queued")
    Local $iQueuedEvent = 0
    For $i = 1 To 200
        $iQueuedEvent = GUIGetMsg()
        If $iQueuedEvent = $g_idCheck Then ExitLoop
    Next
    _Assert($iQueuedEvent = $g_idCheck, "Preserve native button notification in AutoIt's event queue")
    $g_iQueuedAction = 0
    _SetBusy(False)
    _UseIncomingPatch()
    _Assert(GUICtrlRead($g_idPatch) = $sOriginal And $g_sIncoming = "", "Present a queued handoff as a new selection")
    $g_sIncoming = ""
    $g_bBusy = True
    _Assert(Not _ForwardPatch($g_hGUI, $sOriginal), "Reject another patch while busy")
    $g_bBusy = False
    GUICtrlSetState($g_idAutoClose, $GUI_CHECKED)
    $g_bWarnings = True
    _Assert(Not _ShouldAutoClose(), "Keep warnings visible after success")
    $g_bWarnings = False
    _Assert(_ShouldAutoClose(), "Honor normal close-after-success preference")

    $g_sGit = _FindGit()
    If $g_sGit = "" Then
        _Assert(False, "Git is required to complete native integration tests")
    Else
        _TestPatchWorkflow()
    EndIf
    _DestroyGUI()
    ConsoleWrite("Patch to Repo native self-test: " & $g_iTestCount & " checks, " & $g_iTestFailed & " failure(s)." & @CRLF)
    If $g_iTestFailed = 0 Then ConsoleWrite("PATCHTOREPO_SELFTEST_PASS" & @CRLF)
    Return $g_iTestFailed
EndFunc

Func _Assert($bCondition, $sLabel)
    $g_iTestCount += 1
    If Not $bCondition Then
        $g_iTestFailed += 1
        ConsoleWrite("FAIL: " & $sLabel & @CRLF)
    Else
        ConsoleWrite("PASS: " & $sLabel & @CRLF)
    EndIf
EndFunc

Func _TestWrite($sPath, $sText)
    Local $hFile = FileOpen($sPath, $FO_OVERWRITE + $FO_BINARY)
    If $hFile = -1 Then Return False
    Local $iWritten = FileWrite($hFile, StringToBinary($sText, 4))
    FileClose($hFile)
    Return $iWritten <> 0
EndFunc

Func _TestSetAttributes($sPath, $iAttributes)
    Local $aSet = DllCall("kernel32.dll", "bool", "SetFileAttributesW", "wstr", $sPath, "dword", $iAttributes)
    If @error Then Return False
    Return $aSet[0] <> 0
EndFunc

Func _TestProcessPatch($bApply)
    $g_bWarnings = False
    $g_sLog = ""
    GUICtrlSetData($g_idLog, "")
    Local $bResult = _ProcessPatch($bApply, $g_sTestKey & "\History")
    _ReleaseSnapshot()
    Return $bResult
EndFunc

Func _TestPatchWorkflow()
    Local $sRepo = $g_sTempDir & "\repo " & ChrW(0xE4) & " & 100% !"
    Local $sPatch = $g_sTempDir & "\change " & ChrW(0xE4) & " & 100% !.patch"
    Local $sOut = "", $sErr = ""
    DirCreate($sRepo)
    _Assert(_Git($sRepo, "-c init.templateDir= init --quiet", $sOut, $sErr) = 0, "Initialize disposable native repository")
    _Git($sRepo, "config core.autocrlf false", $sOut, $sErr)
    _Git($sRepo, "config core.attributesFile NUL", $sOut, $sErr)
    _TestWrite($sRepo & "\a.txt", "alpha" & @LF & "beta" & @LF & "gamma" & @LF)
    _TestWrite($sRepo & "\b.txt", "one" & @LF & "two" & @LF & "three" & @LF)
    _Assert(_Git($sRepo, "add -- a.txt b.txt", $sOut, $sErr) = 0, "Index baseline native fixture")
    Local $hIndex = FileOpen($sRepo & "\.git\index", $FO_BINARY)
    _Assert($hIndex <> -1, "Open native baseline index")
    Local $bIndex = FileRead($hIndex)
    FileClose($hIndex)
    Local $sPatchText = "diff --git a/a.txt b/a.txt" & @LF & "--- a/a.txt" & @LF & "+++ b/a.txt" & @LF & _
        "@@ -1,3 +1,3 @@" & @LF & " alpha" & @LF & "-beta" & @LF & "+BETA" & @LF & " gamma" & @LF
    _TestWrite($sPatch, $sPatchText)
    _TestSetAttributes($sPatch, 1)
    GUICtrlSetData($g_idPatch, $sPatch)
    ControlSetText($g_hGUI, "", $g_idRepo, $sRepo)
    _Assert(_TestProcessPatch(False), "Check actual AutoIt workflow with read-only patch")
    _Assert(FileRead($sRepo & "\a.txt") = "alpha" & @LF & "beta" & @LF & "gamma" & @LF, "Check leaves working file unchanged")
    _Assert(_TestProcessPatch(True), "Apply after Check in the same AutoIt session")
    _Assert(FileRead($sRepo & "\a.txt") = "alpha" & @LF & "BETA" & @LF & "gamma" & @LF, "Working file matches patch")
    $hIndex = FileOpen($sRepo & "\.git\index", $FO_BINARY)
    _Assert(FileRead($hIndex) = $bIndex, "Actual AutoIt workflow leaves index unchanged")
    FileClose($hIndex)
    _Assert(Not _TestProcessPatch(True), "Reject repeat application")
    _Assert(StringInStr($g_sLog, "already applied") > 0, "Report reverse-check diagnostic")
    _MakeWritable($sPatch)
    _TestWrite($sPatch, "")
    _Assert(Not _TestProcessPatch(True), "Reject empty patch")
    _TestWrite($sPatch, "not a patch" & @LF)
    _Assert(Not _TestProcessPatch(True), "Reject malformed patch")

    _TestWrite($sRepo & "\a.txt", "alpha" & @LF & "beta" & @LF & "gamma" & @LF)
    _TestWrite($sPatch, StringReplace($sPatchText, "+BETA", "+BETA  "))
    _Assert(_TestProcessPatch(True), "Apply a patch with whitespace warnings")
    _Assert($g_bWarnings And Not _ShouldAutoClose(), "Preserve successful-operation warnings")
    _Assert(FileRead($sRepo & "\a.txt") = "alpha" & @LF & "BETA  " & @LF & "gamma" & @LF, "Preserve intended whitespace bytes")

    Local $sModulePatch = "diff --git a/module b/module" & @LF & "index " & _StringRepeat("1", 40) & ".." & _StringRepeat("2", 40) & " 160000" & @LF & _
        "--- a/module" & @LF & "+++ b/module" & @LF & "@@ -1 +1 @@" & @LF & "-Subproject commit " & _StringRepeat("1", 40) & @LF & "+Subproject commit " & _StringRepeat("2", 40) & @LF
    DirCreate($sRepo & "\module")
    _TestWrite($sPatch, $sModulePatch)
    _Assert(Not _TestProcessPatch(True), "Reject submodule-pointer patch in actual AutoIt workflow")
    _Assert(StringInStr($g_sLog, "submodules") > 0, "Give explicit submodule explanation")

    Local $sBlock = "aa" & @LF & "bb" & @LF & "cc" & @LF & "OLD" & @LF & "dd" & @LF & "ee" & @LF & "ff" & @LF
    _TestWrite($sRepo & "\repeat.txt", "padding" & @LF & $sBlock & $sBlock & "ending" & @LF)
    Local $sRepeatedPatch = "diff --git a/repeat.txt b/repeat.txt" & @LF & "--- a/repeat.txt" & @LF & "+++ b/repeat.txt" & @LF & _
        "@@ -2,7 +2,7 @@" & @LF & " aa" & @LF & " bb" & @LF & " cc" & @LF & "-OLD" & @LF & "+NEW" & @LF & " dd" & @LF & " ee" & @LF & " ff" & @LF
    _TestWrite($sPatch, $sRepeatedPatch)
    _Assert(_TestProcessPatch(True), "Apply first repeated-context patch normally")
    Local $sAfterRepeat = FileRead($sRepo & "\repeat.txt")
    _Assert($sAfterRepeat = "padding" & @LF & StringReplace($sBlock, "OLD", "NEW") & $sBlock & "ending" & @LF, "Change only the intended repeated block")
    _Assert(Not _TestProcessPatch(False), "Refuse an ambiguous repeated-context check")
    _Assert(StringInStr($g_sLog, "both directions") > 0, "Explain bidirectional patch ambiguity")
    _Assert(Not _TestProcessPatch(True), "Refuse reapplication at a different matching block")
    _Assert(FileRead($sRepo & "\repeat.txt") = $sAfterRepeat, "Ambiguous retry preserves the untouched second block")

    Local $sPlain = $g_sTempDir & "\not a repo"
    DirCreate($sPlain)
    ControlSetText($g_hGUI, "", $g_idRepo, $sPlain)
    _TestWrite($sPatch, $sPatchText)
    _Assert(Not _TestProcessPatch(True), "Reject non-repository directory")
EndFunc
