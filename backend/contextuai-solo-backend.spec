# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

hiddenimports = ['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'sqlite3', 'aiosqlite', 'apscheduler', 'apscheduler.schedulers.background', 'apscheduler.jobstores.sqlalchemy', 'sqlalchemy', 'pydantic', 'pydantic_settings', 'anyio', 'anyio._backends', 'anyio._backends._asyncio', 'starlette', 'sse_starlette', 'httpx', 'httpx_sse', 'multipart', 'motor', 'asyncpg', 'asyncpg.pgproto.pgproto', 'asyncpg.pgproto', 'asyncpg.protocol', 'asyncpg.protocol.protocol']
hiddenimports += collect_submodules('strands')
hiddenimports += collect_submodules('strands_tools')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('asyncpg')
hiddenimports += ['llama_cpp', 'onnxruntime', 'huggingface_hub', 'tokenizers']

# Native libraries for llama-cpp-python and onnxruntime
extra_binaries = []
try:
    extra_binaries += collect_dynamic_libs('llama_cpp')
except Exception:
    pass
try:
    extra_binaries += collect_dynamic_libs('onnxruntime')
except Exception:
    pass


a = Analysis(
    ['__main__.py'],
    pathex=['.'],
    binaries=extra_binaries,
    datas=[('../agent-library', 'agent-library')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='contextuai-solo-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='contextuai-solo-backend',
)
