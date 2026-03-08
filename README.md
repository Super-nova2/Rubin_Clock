# Rubin Solar Clock (Windows)

Rubin 桌面太阳时钟：显示 Rubin 台址真太阳时、太阳高度角与五级天光状态，并标注是否适合观测。

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
