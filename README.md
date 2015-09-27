Pensive
=======

Pensive is a Python bridge to ENSIME for NeoVim.

Note: The plugin works well enough to be used day-to-day. However, it outputs
a lot of extra information that is useful when debugging. Use at your own risk.


Supported commands
------------------

  * ``EnsimeStart`` - start the ENSIME server
  * ``EnsimeConnect`` - connect to a running instance of the ENSIME server for the current project
  * ``EnsimeUnloadAll`` - unload all information about the current project
  * ``EnsimeTypecheckAll`` - type check all of the files in the current project
  * ``EnsimeTypecheckFile`` - type check the current file
  * ``EnsimeTypeAtPoint`` - get the type info about type under cursor
  * ``EnsimeSymbolAtPoint`` - get info for symbol under cursor
  * ``EnsimeUsesOfSymbolAtPoint`` - find uses of the current symbol in the project Curently populates the quickfix window.
  * ``EnsimeImplicitInfo`` - get info about implicits under the cursor
