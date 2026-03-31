; ContextuAI Solo — NSIS installer hooks
; Adds Windows Firewall rules for the app and its Python sidecar
; so model downloads from HuggingFace work out of the box.

!macro NSIS_HOOK_POSTINSTALL
  ; Allow the main app through Windows Firewall
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="ContextuAI Solo" dir=out action=allow program="$INSTDIR\contextuai-solo.exe" enable=yes profile=any'

  ; Allow the Python sidecar (backend) through Windows Firewall
  ; This is the process that downloads models from huggingface.co
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="ContextuAI Solo Backend" dir=out action=allow program="$INSTDIR\sidecar\contextuai-solo-backend.exe" enable=yes profile=any'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Clean up firewall rules on uninstall
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="ContextuAI Solo"'
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="ContextuAI Solo Backend"'
!macroend
