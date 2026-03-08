# Rubin Solar Clock (Windows)

Rubin 桌面太阳时钟：显示 Rubin 台址真太阳时、当地日期、太阳高度角与五级天光状态，并标注是否适合观测。

内置站点：
- Rubin (Cerro Pachon)
- WFST (Lenghu)

功能特性：
- 无边框悬浮窗，支持边界拖拽缩放
- 中文 / English 双语切换（窗口、托盘、设置）
- 系统托盘常驻与站点快速切换

## 运行要求

- Windows 10/11
- Python 3.12+

## 源码运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 打包 EXE

```powershell
.\build.ps1
```

构建产物位于 `dist\RubinSolarClock.exe`。

## 测试

```powershell
python -m unittest discover -s tests -v
```
