# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for D-PPG Manager."""

import sys
import os

block_cipher = None

# Aggressive exclusions — Anaconda bundles too much
EXCLUDES = [
    # ML/AI
    'torch', 'torchvision', 'torchaudio', 'transformers', 'tensorflow',
    'keras', 'sklearn', 'scikit-learn',
    # Cloud/web
    'botocore', 'boto3', 'google', 'googleapiclient', 'google_auth_oauthlib',
    'google_auth_httplib2', 's3transfer', 'azure',
    # GUI frameworks (we use tkinter only)
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'kivy',
    # Visualization (we only need matplotlib.backends.backend_agg)
    'bokeh', 'panel', 'holoviews', 'plotly', 'seaborn', 'altair', 'dash',
    # Testing/dev
    'pytest', 'IPython', 'jupyter', 'notebook', 'nbconvert', 'nbformat',
    'sphinx', 'docutils', 'jinja2', 'debugpy',
    # Data
    'pandas', 'dask', 'pyarrow', 'fastparquet', 'tables', 'h5py', 'xarray',
    # NLP/text
    'nltk', 'spacy', 'gensim',
    # Browser/web
    'playwright', 'selenium', 'flask', 'django', 'tornado', 'aiohttp',
    'httpx', 'requests_oauthlib',
    # Misc heavy
    'astropy', 'astropy_iers_data', 'sympy', 'numba', 'llvmlite',
    'cryptography', 'paramiko', 'fabric',
    'pygments', 'pyphen', 'emoji', 'conda',
    # Image (we only need PIL basics)
    'cv2', 'skimage', 'imageio',
    # Unused scipy submodules
    'scipy.spatial', 'scipy.integrate', 'scipy.interpolate',
    'scipy.signal', 'scipy.stats', 'scipy.sparse', 'scipy.io',
    'scipy.ndimage', 'scipy.fft', 'scipy.special',
    'scipy.cluster', 'scipy.odr',
    # Unused matplotlib backends
    'matplotlib.backends.backend_qt5agg', 'matplotlib.backends.backend_qt5',
    'matplotlib.backends.backend_wxagg', 'matplotlib.backends.backend_wx',
    'matplotlib.backends.backend_gtk3agg', 'matplotlib.backends.backend_gtk3',
    'matplotlib.backends.backend_tkagg',
]

a = Analysis(
    ['dppg_manager.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'numpy._core._exceptions',
        'numpy._core._methods',
        'numpy._core._dtype_ctypes',
        'numpy._core._internal',
        'scipy.optimize',
        'scipy.optimize._minpack',
        'scipy.optimize._lsq',
        'scipy.optimize._lsq.least_squares',
        'scipy.optimize._lsq.trf',
        'scipy._lib.messagestream',
        'sqlalchemy.dialects.sqlite',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# Filter out unwanted data files from COLLECT
UNWANTED_DATA = {'botocore', 'panel', 'googleapiclient', 'PyQt5', 'torch',
                 'transformers', 'nltk_data', 'bokeh', 'playwright',
                 'astropy_iers_data', 'astropy', 'pyarrow', 'pyphen',
                 'emoji', 'pandas', 'notebook', 'jupyter', 'IPython',
                 'plotly', 'seaborn', 'altair', 'dask', 'sympy'}

a.datas = [d for d in a.datas if not any(uw in d[0] for uw in UNWANTED_DATA)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DPPG Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='dppg.icns' if sys.platform == 'darwin' else 'dppg.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='DPPG Manager',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='DPPG Manager.app',
        icon='dppg.icns',
        bundle_identifier='br.com.amato.dppg-manager',
        info_plist={
            'CFBundleDisplayName': 'DPPG Manager',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'Dr. Alexandre Amato - Instituto Amato',
        },
    )
