; scripts/installer.nsh
; Custom NSIS installer script for Rock Mass Variability Analysis
; Included by electron-builder during Windows build.

; ── Python dependency check ────────────────────────────────────────────────
!macro customInstall
  ; Check if Python 3 is available
  nsExec::ExecToStack '"python" --version'
  Pop $0
  Pop $1

  ${If} $0 != 0
    ; Python not found — offer download
    MessageBox MB_YESNO|MB_ICONINFORMATION \
      "Python 3 was not found on your system.$\n$\n\
Rock Mass Variability Analysis uses a bundled Python environment, but having \
Python 3 installed system-wide is recommended for updates.$\n$\n\
Would you like to open the Python download page?" \
      IDYES openPython IDNO skipPython

    openPython:
      ExecShell "open" "https://www.python.org/downloads/"
    skipPython:
  ${EndIf}
!macroend

!macro customUnInstall
  ; Nothing extra needed on uninstall
!macroend
