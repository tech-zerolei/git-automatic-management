"""Create a per-user desktop launcher; never overwrite an unrelated file."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
try:
    result = subprocess.run(["/usr/bin/xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=True)
    desktop = Path(result.stdout.strip())
except (OSError, subprocess.CalledProcessError):
    desktop = Path.home() / "Desktop"
if not desktop.is_dir():
    raise SystemExit("桌面目录不存在；可直接运行 start.sh。")
def quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
content = "\n".join([
    "[Desktop Entry]", "Type=Application", "Version=1.0", "Name=Git 版本规划（本地版）",
    "Comment=本地只读版本规划，不提交、不发布", "Exec=" + quoted(root / "start.sh"),
    "Icon=" + str(root / "local_app/static/icon.svg"), "Terminal=false", "Categories=Development;",
    "X-Git-Version-Planner=local-0.1", "",
])
target = desktop / "Git-Version-Planner.desktop"
if target.exists():
    if target.is_symlink() or target.read_text() != content:
        raise SystemExit("同名桌面入口已存在且内容不同，未覆盖。")
else:
    with target.open("x") as stream: stream.write(content)
target.chmod(0o755)
result = subprocess.run(["/usr/bin/gio", "set", str(target), "metadata::trusted", "true"], capture_output=True)
print("桌面入口：" + str(target))
if result.returncode:
    print("桌面未接受自动信任；首次使用请右键入口，选择“允许启动”。")
