from pathlib import Path

import shutil
import subprocess
import sys
import tempfile
import urllib.request

try:
    import jsonc
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments' (imported as 'jsonc').\n"
        f"Install it with:\n  {sys.executable} -m pip install json-with-comments\n"
        "Or add it to your project's requirements."
    ) from e

from configure import configure_ocr_model


working_dir = Path(__file__).parent.parent.resolve()
install_path = working_dir / Path("install")
version = len(sys.argv) > 1 and sys.argv[1] or "v0.0.1"

# the first parameter is self name
if sys.argv.__len__() < 4:
    print("Usage: python install.py <version> <os> <arch>")
    print("Example: python install.py v1.0.0 win x86_64")
    sys.exit(1)

os_name = sys.argv[2]
arch = sys.argv[3]


def get_dotnet_platform_tag():
    """自动检测当前平台并返回对应的dotnet平台标签"""
    if os_name == "win" and arch == "x86_64":
        platform_tag = "win-x64"
    elif os_name == "win" and arch == "aarch64":
        platform_tag = "win-arm64"
    elif os_name == "macos" and arch == "x86_64":
        platform_tag = "osx-x64"
    elif os_name == "macos" and arch == "aarch64":
        platform_tag = "osx-arm64"
    elif os_name == "linux" and arch == "x86_64":
        platform_tag = "linux-x64"
    elif os_name == "linux" and arch == "aarch64":
        platform_tag = "linux-arm64"
    else:
        print("Unsupported OS or architecture.")
        print("available parameters:")
        print("version: e.g., v1.0.0")
        print("os: [win, macos, linux, android]")
        print("arch: [aarch64, x86_64]")
        sys.exit(1)

    return platform_tag


def install_deps():
    if not (working_dir / "deps" / "bin").exists():
        print('Please download the MaaFramework to "deps" first.')
        print('请先下载 MaaFramework 到 "deps"。')
        sys.exit(1)

    if os_name == "android":
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
    else:
        shutil.copytree(
            working_dir / "deps" / "bin",
            install_path / "runtimes" / get_dotnet_platform_tag() / "native",
            ignore=shutil.ignore_patterns(
                "*MaaDbgControlUnit*",
                "*MaaThriftControlUnit*",
                "*MaaRpc*",
                "*MaaHttp*",
                "plugins",
                "*.node",
                "*MaaPiCli*",
            ),
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "share" / "MaaAgentBinary",
            install_path / "libs" / "MaaAgentBinary",
            dirs_exist_ok=True,
        )
        shutil.copytree(
            working_dir / "deps" / "bin" / "plugins",
            install_path / "plugins" / get_dotnet_platform_tag(),
            dirs_exist_ok=True,
        )



def install_resource():

    configure_ocr_model()

    shutil.copytree(
        working_dir / "assets" / "resource",
        install_path / "resource",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        working_dir / "assets" / "interface.json",
        install_path,
    )

    # interface.json 里的 icon 字段是相对于 bundle 根目录的路径，
    # 因此图标必须一起拷到 install/ 下，否则打包后界面会退回默认图标。
    for pattern in ("*.png", "*.ico"):
        for icon_file in (working_dir / "assets").glob(pattern):
            shutil.copy2(icon_file, install_path / icon_file.name)

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)

    interface["version"] = version

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    shutil.copy2(
        working_dir / "README.md",
        install_path,
    )
    shutil.copy2(
        working_dir / "LICENSE",
        install_path,
    )


def install_agent():
    shutil.copytree(
        working_dir / "agent",
        install_path / "agent",
        dirs_exist_ok=True,
    )


def get_project_name():
    """读取 assets/interface.json 的 name，作为最终的程序名。"""
    interface_file = working_dir / "assets" / "interface.json"
    project_name = "MaaProject"
    try:
        with open(interface_file, "r", encoding="utf-8") as f:
            project_name = (jsonc.load(f).get("name") or "").strip() or project_name
    except FileNotFoundError:
        print(f"Interface not found: {interface_file}, keep default executable name.")

    # 去掉文件名里不允许的字符，避免生成非法路径
    for ch in '<>:"/\\|?*':
        project_name = project_name.replace(ch, "_")
    return project_name


def install_rename_exe():
    """把 MFAAvalonia 的默认可执行文件名改成 interface.json 里的项目名。

    MFAAvalonia 官方发布包里的可执行文件固定叫 MFAAvalonia(.exe)，
    项目模板的打包流程只是原样拷贝，因此产物会保留这个默认名。
    返回改名后的路径（供 install_set_icon 使用），未找到则返回 None。
    """
    project_name = get_project_name()

    if os_name == "win":
        candidates = [("MFAAvalonia.exe", f"{project_name}.exe")]
    elif os_name == "macos":
        candidates = [("MFAAvalonia.app", f"{project_name}.app")]
    else:
        candidates = [("MFAAvalonia", project_name)]

    for src_name, dst_name in candidates:
        src = install_path / src_name
        dst = install_path / dst_name
        if dst.exists():
            print(f"Skip rename: {dst_name} already exists.")
            return dst
        if not src.exists():
            print(f"Skip rename: {src_name} not found.")
            continue
        src.rename(dst)
        print(f"Renamed {src_name} -> {dst_name}")
        return dst

    return None


RCEDIT_URL = "https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe"


def install_set_icon(exe_path):
    """把 assets/icon.ico 写进 exe 的图标资源（仅 Windows）。

    MFAAvalonia.exe 的图标是编译进 PE 资源的，改文件名不会改变资源管理器里
    显示的图标，只能用 rcedit 之类的工具改写。下载或改写失败都只打印提示，
    不阻塞打包。
    """
    if os_name != "win":
        print(f"Skip icon: only supported on win (current: {os_name}).")
        return

    ico = working_dir / "assets" / "icon.ico"
    if not ico.exists():
        print(f"Skip icon: {ico} not found.")
        return
    if exe_path is None or not exe_path.exists():
        print("Skip icon: executable not found.")
        return

    try:
        cache = Path(tempfile.gettempdir()) / "maae7-rcedit"
        cache.mkdir(parents=True, exist_ok=True)
        rcedit = cache / "rcedit-x64.exe"
        if not (rcedit.exists() and rcedit.stat().st_size > 100_000):
            urllib.request.urlretrieve(RCEDIT_URL, rcedit)
    except Exception as e:  # noqa: BLE001 - 打包不应因此中断
        print(f"Skip icon: failed to fetch rcedit ({e}).")
        return

    try:
        subprocess.run(
            [str(rcedit), str(exe_path), "--set-icon", str(ico)],
            check=True,
            timeout=120,
        )
        print(f"Set icon {ico.name} -> {exe_path.name}")
    except Exception as e:  # noqa: BLE001 - 打包不应因此中断
        print(f"Skip icon: rcedit failed ({e}).")


if __name__ == "__main__":
    install_deps()
    install_resource()
    install_chores()
    install_agent()
    install_set_icon(install_rename_exe())

    print(f"Install to {install_path} successfully.")
