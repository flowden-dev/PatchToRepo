# Third-party notices

The Patch to Repo application source and original document/check artwork use the
project's MIT license. The small checkbox and chevron SVGs also use that license.

| Component | Use | Upstream license / source |
| --- | --- | --- |
| Python | Interpreter, bundled by PyInstaller builds | PSF license; https://www.python.org/psf/license/ |
| Qt / PySide6 / Shiboken6 | Desktop UI and bindings | LGPLv3/GPLv3 or commercial terms as specified upstream; https://doc.qt.io/qtforpython-6/licenses.html |
| Pygments | Syntax highlighting | BSD 2-Clause; https://pygments.org/ |
| PyInstaller | Build tool and frozen-app bootloader | GPLv2+ with distribution exception; https://pyinstaller.org/en/stable/license.html |
| Git / Git for Windows | External patch engine, not bundled | GPLv2; https://git-scm.com/ and https://gitforwindows.org/ |
| pytest / pytest-qt / Ruff / build | Development tools, not runtime components | Their upstream licenses; see installed package metadata |

`licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` contain the unmodified GNU texts.
The packaging script additionally copies license files found in installed Python
distributions. Python and Qt libraries can carry further component-specific
notices; retain the notices supplied with the exact versions you distribute.

A source repository referencing dependencies is different from distributing a
frozen binary containing them. Before publishing a binary under LGPL terms,
provide recipients the required corresponding Qt/PySide/Shiboken source and
notices for the bundled versions, preserve their ability to replace/relink the
libraries, and retain the applicable license texts. Qt source is available from
https://download.qt.io/official_releases/ and
https://code.qt.io/cgit/pyside/pyside-setup.git/ . This project uses an onedir build
with separate shared libraries and places no restriction on replacing them or
reverse engineering for debugging such modifications. A commercial Qt license
is another upstream licensing route.
