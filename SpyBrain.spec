from pathlib import Path
import sysconfig
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    # Avoid collecting incompatible same-name DLLs from unrelated apps on PATH
    # (e.g. Poppler's ICU shadows the Windows ICU used by Qt).
    os.environ['PATH'] = os.pathsep.join([sys.base_prefix, str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']])
datas = [(str(root / 'assets'), 'assets')]
# PhoneInfoga (GPL-3.0) is a separate program that isn't stored in the repository, see bin/README.md.
phoneinfoga_bin = 'phoneinfoga.exe' if IS_WINDOWS else 'phoneinfoga'
if (root / 'bin' / phoneinfoga_bin).is_file():
    datas.append((str(root / 'bin' / phoneinfoga_bin), 'bin'))
hiddenimports = []
if IS_WINDOWS:
    hiddenimports += ['winloop._noop']
    # tomli's Windows wheel imports a mypyc extension whose generated name is not
    # visible to static import analysis. Derive it from the build environment.
    hiddenimports += [p.name.split('.')[0] for p in Path(sysconfig.get_path('purelib')).glob('*__mypyc*.pyd')]
for package in ('sherlock_project', 'maigret', 'theHarvester', 'geoclip'):
    datas += collect_data_files(package)
    # GeoCLIP's training code isn't needed to predict.
    hiddenimports += collect_submodules(package, filter=lambda name: not name.startswith('geoclip.train'))
# Photo location: GeoCLIP runs on PyTorch + transformers (CLIP); transformers checks
# installed versions through package metadata, so ship it for its dependencies too.
hiddenimports += collect_submodules('transformers.models.clip') + ['geolocate', 'leaks']
for distribution in ('sherlock-project', 'maigret', 'theHarvester', 'geoclip', 'torch', 'torchvision', 'transformers',
                     'tokenizers', 'huggingface-hub', 'safetensors', 'regex', 'tqdm', 'filelock', 'packaging', 'numpy',
                     'pyyaml', 'requests', 'anthropic', 'httpx', 'pydantic'):
    datas += copy_metadata(distribution)
# torchvision loads its ops from _C_stable.pyd/.so (and image_stable) by path at import time;
# PyInstaller's hook doesn't know these names, so ship them next to the package.
torchvision_dir = Path(sysconfig.get_path('purelib')) / 'torchvision'
if IS_WINDOWS:
    torchvision_libs = [*torchvision_dir.glob('*.pyd'), *torchvision_dir.glob('*.dll')]
else:
    torchvision_libs = [*torchvision_dir.glob('*.so'), *torchvision_dir.glob('*.so.*')]
binaries = [(str(f), 'torchvision') for f in torchvision_libs]
a = Analysis([str(root / 'app.py')], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['IPython', 'matplotlib', 'pytest', 'tkinter', 'PySide6.QtQml', 'PySide6.QtQuick',
              'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtPdf', 'PySide6.QtTest'],
    noarchive=False)
# Qt 6.12 uses the Windows ICU API. Third-party ICU builds with renamed
# symbols (ucnv_open_78 etc.) must not shadow it in a cached analysis either.
a.binaries = [entry for entry in a.binaries if 'codex-runtimes' not in entry[1].lower()]
pyz = PYZ(a.pure)
# The .ico is a Windows resource; PyInstaller ignores it on other platforms.
icon = str(root / 'assets' / 'hub.ico') if IS_WINDOWS else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SpyBrain',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SpyBrain')
