# 截图识字 v0.2

本地离线的 Windows 截图 OCR 小工具。支持多张截图依次识别、按图片编辑与复制，以及一键复制全部文字。

## 直接使用

双击 `dist/ScreenshotOCR.exe`。只需这一个文件，可以复制到其他文件夹运行，无需安装 Python。模型已经内置，首次识别不下载文件。

1. 点击「添加图片（可多选）…」，按住 Ctrl 或 Shift 选择多张 PNG / JPG / BMP / WebP 图片。
2. 图片按左侧列表顺序依次识别，列表会显示每张的状态。
3. 点击列表中的图片，在中间查看原图，在右侧修改文字。切换图片会保留当前修改。
4. 点击「复制当前图片」，只复制选中的那张图片的文字。
5. 点击「复制全部文字」，按列表顺序复制所有非空结果，图片之间以一个空行分隔，不添加文件名。复制内容包含手动修改。

也可以先按 `Win+Shift+S` 截图，再点击「粘贴截图」或按 `Ctrl+V`，每次会追加一张到列表。再次添加文件同样追加，不替换已有结果。
编辑区聚焦时，`Ctrl+V` 支持粘贴普通文本；剪贴板含图片时会追加新的识别任务。
识别过程中可以查看、编辑、复制已完成的图片；添加图片和复制全部在队列结束后可用。
没有文字或处理失败的图片保留在列表，复制全部时跳过；单张失败不会阻断后面的识别。
点击「清空列表」可以重新开始一组识别。

图片与识别结果只在内存中处理，应用不保存历史记录，也不上传图片。关闭后不会恢复结果。
单文件 EXE 运行时会把程序组件和模型解压到系统临时目录，退出时由打包运行时清理；这不是截图历史。启动耗时与磁盘、系统扫描等因素有关。

目标平台：Windows 10/11 x64，普通 CPU 即可。本次实测环境为 Windows 11 x64；尚未在全新 Windows 10 系统或 ARM 系统验证。

## 当前范围与限制

- 主要面向清晰的中英文电脑截图。
- 按检测到的文本行输出，不还原表格、分栏或原始排版。
- 英文空格、小字、特殊符号可能识别错误，复制前可手动修改。
- 不包含截图热键注册、后台驻留、PDF、历史记录或云端模型。
- 识别在后台线程执行；识别完成后可关闭窗口。

## 开发与构建

建议使用 Python 3.12 x64。已记录实际构建依赖版本：`requirements-lock.txt`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe app.py
```

运行集成检查（自动生成不含个人信息的测试图片）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

构建单文件成品：

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

打包方案为 PyInstaller onefile，使用 PySide6 界面、RapidOCR ONNX Runtime CPU 引擎和随包内置的 PP-OCRv4 模型。图标由项目代码绘制。
`ScreenshotOCR.spec` 显式收集模型、配置和本地运行库，依赖许可说明收集在 `third_party/` 并嵌入 EXE。

打包后，可用内置诊断入口验证成品的模型、界面和复制路径：

```powershell
.\.venv\Scripts\python.exe tests\generate_sample.py
.\.venv\Scripts\python.exe tests\verify_portable.py
```

诊断入口在完成后输出 JSON 和窗口预览 PNG，并退出。普通双击运行不会生成这些文件。

## 交付验证

- 集成检查覆盖多文件选择、逐图识别、后台识别时编辑已完成图片、切换保存、复制当前、按顺序复制全部、粘贴追加、清空列表、空白图片和无效图片。
- 成品测试会复制 EXE 到独立中文目录，从 PATH 移除 Python，再识别两张内容不同的图片，检查两种复制结果并保存窗口预览。
- 可通过 `.\.venv\Scripts\python.exe tests\verify_portable.py` 重现成品检查。
- 本次验证环境为 Windows 11 x64，不等同于全新操作系统测试。
- Windows ICU 由系统提供；构建规则排除了开发机 PATH 中 Poppler 的同名 ICU DLL，防止误打包。
