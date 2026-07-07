# Compatibility wrapper notice

The old backend-named diagnostic entry points now launch the standalone remote Alleva diagnostics tool.

Use this instead:

```text
Run-AllevaRemoteDiagnostics.cmd
```

Current script version: `2026-07-06-r3-remote-alleva-diagnostics-6`.

This tool bypasses the IZ Clinical Notes Analyzer app and calls Alleva remote REST endpoints directly. The raw treatment-plan field export now streams all plans/all fields directly to final output files to avoid memory growth.


Compatibility wrapper points to remote diagnostics package version 2026-07-06-r3-remote-alleva-diagnostics-7.
