# Patch to Repo icon

- `PatchToRepo.ico`: Windows icon container with 16, 20, 24, 32, 40, 48, 64, 128, and 256 pixel images.
- `PatchToRepo.png`: original large transparent artwork.
- The ICO is embedded at compilation. A compiled installation does not need these external files at runtime.
- Each ICO image uses 32-bit color with an alpha channel for transparency.

## Integration

Keep this folder beside `PatchToRepo.au3` when compiling. `Compile-Windows.cmd` embeds the ICO into the x64 EXE through the shared build script. Native compiler and SciTE wrapper icon settings are also included in the source.

Compiled installations use the embedded icon for the context menu, window, and Start menu shortcuts. Source installations copy the ICO to a stable location under `%LOCALAPPDATA%\PatchToRepo\assets` so moving the downloaded source folder does not break the installed menu icon.

Use `PatchToRepo.png` as the master when preparing additional sizes. Preserve transparency and include the small images needed for Explorer menus and display scaling.
