"""Build dist/Orbit/Orbit.exe (PyInstaller, one folder) for Windows.

    pip install -r requirements.txt pyinstaller pillow
    python packaging/windows/build_exe.py

Then packaging/windows/orbit.iss (Inno Setup) wraps dist/Orbit into OrbitSetup.exe.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"


def make_ico() -> Path:
    from PIL import Image
    BUILD.mkdir(exist_ok=True)
    ico = BUILD / "orbit.ico"
    Image.open(ROOT / "orbit" / "ui" / "icons" / "orbit.png").save(
        ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def main():
    ico = make_ico()
    sep = ";"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", "Orbit",
        "--icon", str(ico),
        "--add-data", f"orbit/ui/qml{sep}orbit/ui/qml",
        "--add-data", f"orbit/ui/icons{sep}orbit/ui/icons",
        "--add-data", f"config.toml{sep}.",
        "--collect-submodules", "orbit.platform.windows",
        "--collect-submodules", "winrt",
        "--collect-submodules", "pycaw",
        "--collect-submodules", "comtypes",
        "--hidden-import", "uiautomation",
        "--exclude-module", "PIL", "--exclude-module", "pytest", "--exclude-module", "tkinter",
        "--hidden-import", "orbit.ui.settings_window",
        "--version-file", str(version_file()),
        "packaging/orbit_main.py",
    ]
    subprocess.check_call(args, cwd=ROOT)
    prune(ROOT / "dist" / "Orbit" / "_internal")
    print("built", ROOT / "dist" / "Orbit" / "Orbit.exe")


# Qt parts Orbit never loads (the overlay uses QtQuick + Shapes + Effects, settings use
# Widgets). PyInstaller's PySide6 hook collects everything; this keeps the app ~120 MB
# instead of ~440 MB. tools/startup_check-style smoke test runs on the result in CI.
UNUSED_QT = ("WebEngine", "WebChannel", "WebSockets", "WebView", "Pdf", "Quick3D", "3D", "Charts",
             "Graphs", "DataVisualization", "Location", "Positioning", "Multimedia", "SpatialAudio",
             "TextToSpeech", "RemoteObjects", "Scxml", "StateMachine", "Sensors", "SerialPort",
             "SerialBus", "Bluetooth", "Nfc", "Test", "VirtualKeyboard", "Designer", "Help",
             "UiTools", "Sql", "Concurrent", "HttpServer", "Protobuf", "Grpc", "QuickTimeline",
             "Lottie", "5Compat")


def prune(internal: Path):
    import shutil
    qt = internal / "PySide6"
    removed = 0
    for f in list(qt.glob("Qt6*.dll")) + list(qt.glob("Qt*.pyd")) + list(qt.glob("Qt*.pyi")):
        name = f.stem.removeprefix("Qt6").removeprefix("Qt")
        if any(name.startswith(u) for u in UNUSED_QT):
            removed += f.stat().st_size
            f.unlink()
    for d in list((qt / "qml").glob("*")):
        if d.is_dir() and any(d.name.removeprefix("Qt").startswith(u) for u in UNUSED_QT):
            removed += sum(x.stat().st_size for x in d.rglob("*") if x.is_file())
            shutil.rmtree(d)
    for extra in ("translations", "opengl32sw.dll", "QtWebEngineProcess.exe", "resources"):
        p = qt / extra
        if p.exists():
            removed += p.stat().st_size if p.is_file() else sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    print(f"pruned {removed / 1e6:.0f} MB of unused Qt")


def version_file() -> Path:
    from orbit import __version__ as v
    nums = (v.split("+")[0].split(".") + ["0", "0", "0"])[:4]
    t = ", ".join(n if n.isdigit() else "0" for n in nums)
    f = BUILD / "version.txt"
    f.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({t}), prodvers=({t})),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Orbit'),
    StringStruct('FileDescription', 'Orbit - CMF Buds Pro 2 dial controller'),
    StringStruct('FileVersion', '{v}'),
    StringStruct('ProductName', 'Orbit'),
    StringStruct('ProductVersion', '{v}')])]),
  VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")
    return f


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
