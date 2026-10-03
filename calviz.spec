# PyInstaller build recipe:  pyinstaller calviz.spec
# Produces a single-file, windowed dist/CalendarVisualizer.exe

a = Analysis(
    ["run_calviz.py"],
    datas=[
        ("calviz/assets", "calviz/assets"),
        ("AI_SYNTAX_GUIDE.md", "."),
        ("examples/sample.md", "examples"),
    ],
    excludes=["numpy", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="CalendarVisualizer",
    icon="calviz/assets/icon.ico",
    console=False,
    upx=False,
)
