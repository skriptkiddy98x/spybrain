# bin/

SpyBrain's phone scan can use [PhoneInfoga](https://github.com/sundowndev/phoneinfoga) (GPL-3.0), a separate program.
It isn't stored in this repository. To use it, or to build the bundle (the build copies it), download release
**v2.11.0** from https://github.com/sundowndev/phoneinfoga/releases/tag/v2.11.0, then put the program in this folder:

- **Windows:** rename it to `phoneinfoga.exe`.
- **Linux / macOS:** rename it to `phoneinfoga` (no extension) and make it executable: `chmod +x bin/phoneinfoga`.

Without it everything else works, and the phone scan reports PhoneInfoga as "Not installed".
