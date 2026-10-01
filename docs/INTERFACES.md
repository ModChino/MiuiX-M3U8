# MiuiX M3U8 架构与接口契约（冻结版 v1）

> 目标：为 N_m3u8DL-RE 提供一个 **Miuix / 小米澎湃 OS 视觉风格** 的 Windows 桌面下载器。
> 本文件是并行开发的**唯一接口契约**。实现方必须严格按签名实现；调用方按签名调用，不得自行改签名。
> 如需变更契约，先通知 Lead，由 Lead 统一修改本文件。

---

## 1. 技术选型（已定，不再讨论）

**Python 3.12 + PySide6 6.11（Qt 6） + 自研 Miuix 设计系统**

| 候选 | 结论 | 理由 |
|---|---|---|
| **PySide6 / Qt6** | ✅ **采用** | C++ 原生渲染、Windows 上最稳；**不依赖 WebView，彻底规避 Tauri 的 WebView2 黑屏/白屏**；参考项目 Fluent-M3U8 同栈已验证；可离屏渲染截图自验证；PyInstaller 一条命令出 exe |
| Tauri | ❌ | 用户已遇到 WebView2 黑屏白屏；且重活都在 N_m3u8DL-RE 子进程，Web 层性能优势用不上 |
| Compose Multiplatform + Miuix 官方库 | ❌ | 视觉最正统，但需引入 JDK+Gradle+Kotlin 全套工具链（首次构建 1GB+ 依赖），JVM 冷启动 1–2s、内存 300MB+，且 Windows 产物无法在开发机交叉打包 |
| C++ Qt | ❌ | 性能增益对本项目（GUI 只做表单+日志+进度）无意义，开发/迭代成本翻倍 |

**Miuix 视觉风格**用 QSS + 少量自绘控件复刻（token 见 `app/miuix/tokens.py`），不引入 miuix kotlin 依赖。

---

## 2. 目录结构与写作用域（**严格不得越界**）

```
MiuiX-M3U8/
├── app/
│   ├── main.py                 [C] 入口：init_theme → MainWindow → exec
│   ├── miuix/                  [A] 设计系统
│   │   ├── __init__.py
│   │   ├── tokens.py           颜色/字号/圆角/间距 token
│   │   ├── theme.py            ThemeManager + QSS 生成
│   │   ├── widgets.py          基础组件
│   │   └── icons.py            SVG 图标
│   ├── core/                   [B] 核心引擎（纯逻辑，不 import QtWidgets）
│   │   ├── __init__.py
│   │   ├── model.py            DownloadOptions / DownloadTask / TaskStatus
│   │   ├── nm3u8dl.py          参数 → 命令行
│   │   ├── parser.py           stdout 行 → Event
│   │   ├── runner.py           TaskRunner（subprocess + 读线程）
│   │   ├── server.py           浏览器扩展的本地接收端
│   │   ├── updater.py          内核版本检测 / 下载更新（纯标准库，不 import Qt）
│   │   └── config.py           Config 持久化 + 依赖探测
│   └── ui/                     [C] 页面
│       ├── __init__.py
│       ├── window.py           MainWindow
│       ├── taskcard.py         任务卡片
│       ├── updater_ui.py       更新卡片的 Qt 胶水层（信号桥）
│       └── pages/
│           ├── __init__.py
│           ├── download.py     新建下载
│           ├── tasks.py        任务列表
│           └── settings.py     设置
├── tests/                      [B] 自检（pytest 不必须，可直接 python 运行）
├── tools/                      [Lead] 放 N_m3u8DL-RE.exe / ffmpeg.exe
├── docs/                       [Lead]
├── requirements.txt            [D]
├── run.bat / build.bat         [D]
└── README.md                   [D]
```

---

## 3. 模块 A：`app/miuix/` —— 设计系统契约

### 3.1 tokens.py

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Palette:
    primary: str; on_primary: str
    primary_container: str; on_primary_container: str
    secondary: str; on_secondary: str
    secondary_container: str; on_secondary_container: str
    tertiary: str; on_tertiary: str
    tertiary_container: str; on_tertiary_container: str
    background: str; on_background: str
    surface: str; on_surface: str
    surface_container: str            # 卡片背景
    surface_container_high: str       # 输入框/次级卡片
    on_surface_variant: str           # 次要文字
    outline: str; outline_variant: str
    error: str; on_error: str; error_container: str
    success: str; warning: str
    disabled: str; on_disabled: str
    scrim: str

LIGHT: Palette
DARK: Palette

@dataclass(frozen=True)
class TextStyle:
    size: int          # px
    weight: int        # QFont.Weight 数值（400/500/600/700）
    line_height: int   # px

TEXT: dict[str, TextStyle]   # 键至少含: title1 title2 headline body1 body2 label caption mono

FONT_STACK: list[str]        # 首选字体族，按优先级：MiSans → 微软雅黑 → ...
RADIUS: dict[str, int]       # 键: xs sm md lg xl pill
SPACING: dict[str, int]      # 键: xs sm md lg xl page
ICON_SIZE: dict[str, int]    # 键: sm md lg
```

### 3.2 theme.py

```python
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

class ThemeManager(QObject):
    changed = Signal()                    # 主题切换后发出；所有自绘控件必须连它并 update()
    def __init__(self, app: QApplication): ...
    @property
    def palette(self) -> Palette: ...
    @property
    def dark(self) -> bool: ...
    def mode(self) -> str: ...            # "system" | "light" | "dark"
    def set_mode(self, mode: str) -> None: ...   # 触发 changed + 重新 apply
    def qss(self) -> str: ...
    def apply(self) -> None: ...          # app.setStyleSheet + app.setFont

def init_theme(app: QApplication) -> ThemeManager: ...
def theme() -> ThemeManager: ...          # 全局访问；未初始化则抛 RuntimeError
```

**QSS 约定**：所有组件类以 `Miuix` 开头，QSS 选择器用类名匹配，例如
`.MiuixCard { background: %(surface_container)s; border-radius: %(lg)dpx; }`
主题切换时重新生成并 `app.setStyleSheet()`。动态属性用 `setProperty("variant","filled")` + `[variant="filled"]` 选择器。

### 3.3 widgets.py（**C 只能使用下列公开类，禁止直接 new 原生 Qt 控件做界面**）

```python
class MiuixCard(QFrame):          # .body: QVBoxLayout；构造 MiuixCard(parent=None, padding=16)
class MiuixButton(QPushButton):   # MiuixButton(text, parent=None, variant="filled", icon=None)
                                  # variant: "filled" | "tonal" | "text" | "outlined" | "danger"
                                  # .setVariant(v); 高度 40；pill 圆角
class MiuixIconButton(QPushButton):  # MiuixIconButton(icon_name: str, parent=None, size=36, tooltip="")
class MiuixLineEdit(QLineEdit):   # 高度 44，圆角 md，focus 时 primary 边框
class MiuixTextEdit(QPlainTextEdit)
class MiuixComboBox(QComboBox)    # 高度 44
class MiuixSwitch(QCheckBox):     # 自绘胶囊开关，52x32；信号 toggled(bool) 由 QCheckBox 提供
class MiuixCheckBox(QCheckBox)
class MiuixProgressBar(QProgressBar):  # 自绘圆角条；setValue(0..1000)，内部按 0..1000，显示用 percent()
class MiuixSlider(QSlider):       # Qt.Horizontal
class MiuixLabel(QLabel):         # MiuixLabel(text, style="body1", color=None, parent=None)
class MiuixTopBar(QWidget):       # MiuixTopBar(title: str, back: bool = False)；信号 backClicked()
class MiuixNavRail(QWidget):      # 侧边导航；addItem(icon_name, text) -> int；信号 currentChanged(int)；setCurrentIndex(i)
class MiuixSectionHeader(QWidget):# MiuixSectionHeader(text)
class MiuixListItem(QWidget):     # MiuixListItem(title, subtitle="", icon=None, trailing=None)
                                  # 信号 clicked()；trailing 为 QWidget 时右对齐
class MiuixSegmented(QWidget):    # 分段控件；addItem(text)；信号 currentChanged(int)；currentIndex()
class MiuixScrollArea(QScrollArea):  # 无边框、透明背景、平滑滚动
class MiuixBadge(QLabel):         # MiuixBadge(text, tone="neutral")；tone: neutral|success|error|warning|primary
class MiuixDialog(QDialog):       # 圆角无边框对话框基类；setBodyLayout(layout)；addButton(text, variant) -> MiuixButton
def toast(parent: QWidget, text: str, tone: str = "neutral") -> None   # 顶部淡入淡出提示
```

### 3.3b 精确视觉数值（**最高优先级，覆盖本文件 §3 中任何凭印象写的尺寸**）

> 完整 token 表（53 个颜色 Light/Dark + 14 个文本样式 + 全组件规格 + squircle 算法）见 **`docs/MIUIX_TOKENS.md`**（数值来自 miuix 源码 tarball 逐行抄录，带源文件行号）。
> 与本文件冲突时**一律以 MIUIX_TOKENS.md 为准**。以下是最容易搞错的几条：

- primary = **#3482FF**(Light) / **#277AF7**(Dark)；background #FFFFFF/#242424；surface #F7F7F7/#000000；**surfaceContainer(Card 底) #FFFFFF/#242424**；secondaryVariant(默认按钮底) #F0F0F0/#434343；outline #D9D9D9/#404040
- 带 alpha 的 token 要保留 alpha：onSurfaceSecondary 80%、onSurfaceVariantSummary 60%/50%、onSurfaceVariantActions 40%、windowDimming 30%/60%
- 文本只有 `subtitle` 加粗(700)，只有 `paragraph` 有 1.2em 行高，**全部无 letter-spacing**。字号直接用 px：32/24/20/18/17/16/14/13/11
- **Card**：圆角 16dp，squircle，无边框无阴影，InsideMargin 默认 0
- **Button**：圆角 **16dp 不是胶囊**，最小 58×40，padding h16/v13，字 17px
- **Switch**：轨道 **49×28**（非 52×32），thumb 20，未选中偏移 4 → 选中 25，按压缩放 ×1.127
- **Slider**：轨道即 **28dp 粗胶囊**，thumb 直径 20.16 画在胶囊**内部**
- **TopAppBar** 折叠高 52，标题水平内边距 26；**NavigationBar** 项高 64 / 图标 26 / 标签 12px；列表项最小高 56、padding 16；**页面左右边距 26**
- **Squircle 必须自绘**：`tile = r*1.1`、`handle = tile*0.357`，四段 cubicTo（算法见 MIUIX_TOKENS.md §4）。QSS border-radius 只能近似(≈0.9r)，且**不裁剪子控件**，需 setMask/setClipPath。

### 3.4 icons.py

```python
def icon(name: str, color: str | None = None, size: int = 20) -> QIcon: ...
ICON_NAMES: set[str]
# 必须支持: download list settings info play pause stop trash folder link check
#          close chevron_right chevron_down plus refresh sun moon copy alert search
#          film music subtitles clock speed shield file key tools external
```
实现方式：内联 SVG path 字符串 + QSvgRenderer 渲染成 QPixmap（`PySide6.QtSvg` 随 pyside6-essentials 提供）。`color` 为 None 时使用当前主题的 on_surface。

---

## 4. 模块 B：`app/core/` —— 核心引擎契约

> **不得 import 任何 QtWidgets**（runner.py 可用 QtCore 的 QProcess/QObject/Signal）。

### 4.1 model.py —— 见上文字段表（Lead 已写入，直接用，不要删字段）

### 4.2 nm3u8dl.py

```python
def build_command(exe: str, opt: DownloadOptions) -> list[str]: ...
def preview_command(exe: str, opt: DownloadOptions) -> str: ...   # 可复制到 cmd 的单行命令，含引号
```
规则：只把**非默认值**写入命令行；`opt.extra_args` 原样追加在最后（最高优先级）。
N_m3u8DL-RE 真实参数以 v0.6.0-beta `--help` 为准（见 `docs/NM3U8DL_CLI.md`）。

### 4.3 parser.py

```python
@dataclass
class Event:
    kind: str                       # "info" | "progress" | "mux" | "done" | "error" | "selected"
    percent: float | None = None
    speed: str | None = None
    size: str | None = None
    segments_done: int | None = None
    segments_total: int | None = None
    eta: str | None = None
    path: str | None = None
    text: str = ""

class OutputParser:
    def feed(self, chunk: str) -> list[Event]: ...    # 支持 \r 分帧 + ANSI 剥离
    def reset(self) -> None: ...
```

### 4.4 runner.py

```python
class TaskRunner(QObject):
    taskAdded    = Signal(str)            # task_id
    taskUpdated  = Signal(str)            # task_id
    taskFinished = Signal(str, int)       # task_id, exit_code
    def __init__(self, parent=None, max_concurrent: int = 2): ...
    def set_exe(self, path: str) -> None: ...
    def set_max_concurrent(self, n: int) -> None: ...
    def exe(self) -> str: ...
    @property
    def tasks(self) -> list[DownloadTask]: ...        # 新→旧
    def get(self, task_id: str) -> DownloadTask | None: ...
    def submit(self, opt: DownloadOptions) -> str: ...
    def cancel(self, task_id: str) -> None: ...
    def retry(self, task_id: str) -> str: ...
    def remove(self, task_id: str) -> None: ...
    def clear_finished(self) -> list[str]: ...        # 返回被移除的 id
```
要求：QProcess 以合并 stderr 方式读取；实时把 stdout 交给 OutputParser 并更新 task 字段后发 taskUpdated（**节流到 ≥80ms 一次**，避免刷爆 UI）；完成后从日志里解析最终文件路径写入 `task.output_path`。

### 4.5 config.py

```python
@dataclass
class Config:
    theme_mode: str = "system"
    nm3u8dl_path: str = ""
    ffmpeg_path: str = ""
    save_dir: str = ""
    max_concurrent: int = 2
    window_geometry: str = ""
    defaults: DownloadOptions = field(default_factory=DownloadOptions)
    @staticmethod
    def file() -> Path: ...          # <程序所在目录>/config.json（便携版：拷目录即带走配置）
                                     # 目录只读时回退 %APPDATA%/MiuiX-M3U8/（非 Windows 用 ~/.config/MiuiX-M3U8/）
                                     # 读取时若新位置没有，会去上面这个老位置找一次（迁移）
    @staticmethod
    def load() -> "Config": ...
    def save(self) -> None: ...      # 原子写

def detect_tools(base_dir: Path | None = None) -> dict[str, str]:
    # 返回 {"nm3u8dl": path|"", "ffmpeg": path|"", "mp4decrypt": path|"", "shaka": path|""}
    # 查找顺序：配置路径 → <项目>/tools → PATH
```

---

## 5. 模块 C：`app/ui/` —— 页面契约

- `MainWindow(QMainWindow)`：左侧 `MiuixNavRail`（下载 / 任务 / 设置 / 关于）+ 右侧 `QStackedWidget`。
- 三页签名：`DownloadPage(runner: TaskRunner, config: Config, parent=None)`、`TasksPage(runner, config, parent=None)`、`SettingsPage(runner, config, parent=None)`。
  每页暴露 `def refresh(self) -> None`。
- 页面 → 主导航的跳转通过页面信号 `gotoRequested = Signal(int)` 冒泡给 MainWindow。
- 三页之间共享的 `runner`/`config` 由 `main.py` 创建并注入；**页面不得自己 new TaskRunner / 重新 load Config**。
- 主题切换由设置页调用 `theme().set_mode(...)`，并写回 `config.theme_mode`。
- 新建下载成功后调用 `runner.submit(...)` 并 `gotoRequested.emit(1)`。

## 6. 交付与验证

- 所有实现必须能在 **offscreen** 下无异常渲染：`QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import app.main"`
- 截图自检脚本：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m verify.shot [页面名]`（[D] 提供）
- Windows 交付：`run.bat`（创建 venv + 装依赖 + 启动）、`build.bat`（PyInstaller 打包）
