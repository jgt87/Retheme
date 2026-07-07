Retheme - PowerShell portable package
================================================

No installation, no admin rights, no compiled executable:
- runtime\python.exe is an official signed CPython interpreter
- app\ is the tool's source code, libs\ its dependencies

Start (either works):
  * double-click "Start Retheme.cmd"
  * or in PowerShell:  .\'Start Retheme.ps1'

The web UI opens in your browser automatically. Close the console window
to stop the tool.

Command line (extract/apply/restyle/audit), e.g.:
  .\'Start Retheme.ps1' extract template.potx -o package\
