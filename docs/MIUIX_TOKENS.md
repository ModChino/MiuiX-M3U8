# Miuix 设计 Token 精确数值表（用于 Qt/PySide6 像素级复刻）

> 来源优先级：**源码为准**。所有数值均从仓库源码逐字抄录，文档数值与其一致（已交叉验证）。
> 仓库：`miuix-kotlin-multiplatform/miuix`（抓取时已更名为 `compose-miuix-ui/miuix`，API 会 301 重定向；Maven 坐标仍为 `top.yukonga.miuix.kmp`），默认分支 `main`，抓取时间 2026-09-30。
>
> ⚠️ **文档 URL 更正**：用户给出的 `guide/theme-system`、`guide/text-styles` 均为 **404**。
> 正确路径为 `guide/theme`、`guide/textstyles`（无连字符）。下列 URL 均已验证返回 200。

## 0. 来源 URL 清单

| 内容 | URL |
|---|---|
| 主题系统文档 | https://compose-miuix-ui.github.io/miuix/zh_CN/guide/theme |
| 颜色文档 | https://compose-miuix-ui.github.io/miuix/zh_CN/guide/colors |
| 文本样式文档 | https://compose-miuix-ui.github.io/miuix/zh_CN/guide/textstyles |
| 平滑圆角文档 | https://compose-miuix-ui.github.io/miuix/zh_CN/guide/squircle |
| 组件索引 | https://compose-miuix-ui.github.io/miuix/zh_CN/components/ |
| **Colors.kt（颜色权威来源）** | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/theme/Colors.kt |
| **TextStyles.kt（文本权威来源）** | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/theme/TextStyles.kt |
| MiuixTheme.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/theme/MiuixTheme.kt |
| SquirclePath.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-squircle/src/commonMain/kotlin/top/yukonga/miuix/kmp/squircle/SquirclePath.kt |
| Squircle SDF 烘焙参数 | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-squircle/build.gradle.kts |
| Squircle 着色器 | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-squircle/src/commonMain/kotlin/top/yukonga/miuix/kmp/squircle/SquircleBackground.kt |
| Card.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/Card.kt |
| Button.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/Button.kt |
| Switch.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/Switch.kt |
| Slider.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/Slider.kt |
| TopAppBar.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/TopAppBar.kt |
| NavigationBar.kt | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/NavigationBar.kt |
| Component.kt（列表项） | https://github.com/compose-miuix-ui/miuix/blob/main/miuix-ui/src/commonMain/kotlin/top/yukonga/miuix/kmp/basic/Component.kt |

### 关于「文档截图」
Miuix 文档**没有静态截图文件**（`docs/public/` 下只有一个 `Icon.webp`）。每个组件页顶部内嵌的是
**实时 Compose-Wasm 交互 demo 的 iframe**，形如 `../../compose/index.html?id=<组件名>`。
在线可访问的 demo URL（已逐个验证 HTTP 200）：

~~~
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=card
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=button
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=switch
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=slider
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=topappbar
https://compose-miuix-ui.github.io/miuix/compose/index.html?id=navigationbar
~~~
组件文档页：`https://compose-miuix-ui.github.io/miuix/zh_CN/components/<组件名>`

---

# 1. 颜色 Token 完整表（54 个 token，Light / Dark）

来源：`Colors.kt` L341–L559。全部为 8 位 ARGB。Qt 中 `#AARRGGBB` 可直接用；
QSS 里带 alpha 的项需写 `rgba(r,g,b,a)`。

| # | Token | Light | Light alpha | Dark | Dark alpha |
|---:|---|---|---|---|---|
| 1 | `primary` | `#3482FF` | opaque | `#277AF7` | opaque |
| 2 | `onPrimary` | `#FFFFFF` | opaque | `#FFFFFF` | opaque |
| 3 | `primaryVariant` | `#3482FF` | opaque | `#0073DD` | opaque |
| 4 | `onPrimaryVariant` | `#AECDFF` | opaque | `#99C7F1` | opaque |
| 5 | `error` | `#E94634` | opaque | `#F12522` | opaque |
| 6 | `onError` | `#FFFFFF` | opaque | `#FFFFFF` | opaque |
| 7 | `errorContainer` | `#FDF6F4` | opaque | `#2E0603` | opaque |
| 8 | `onErrorContainer` | `#410002` | opaque | `#FFDAD6` | opaque |
| 9 | `disabledPrimary` | `#C2D9FF` | opaque | `#253E64` | opaque |
| 10 | `disabledOnPrimary` | `#F3F8FF` | opaque | `#677993` | opaque |
| 11 | `disabledPrimaryButton` | `#C2D9FF` | opaque | `#253E64` | opaque |
| 12 | `disabledOnPrimaryButton` | `#FFFFFF` | opaque | `#677893` | opaque |
| 13 | `disabledPrimarySlider` | `#B8CFF5` | opaque | `#44587C` | opaque |
| 14 | `primaryContainer` | `#5D9BFF` | opaque | `#338FE4` | opaque |
| 15 | `onPrimaryContainer` | `#FFFFFF` | opaque | `#FFFFFF` | opaque |
| 16 | `secondary` | `#E6E6E6` | opaque | `#505050` | opaque |
| 17 | `onSecondary` | `#FFFFFF` | opaque | `#FFFFFF` | opaque |
| 18 | `secondaryVariant` | `#F0F0F0` | opaque | `#434343` | opaque |
| 19 | `onSecondaryVariant` | `#303030` | opaque | `#D9D9D9` | opaque |
| 20 | `disabledSecondary` | `#F0F0F0` | opaque | `#3F3F3F` | opaque |
| 21 | `disabledOnSecondary` | `#FCFCFC` | opaque | `#797979` | opaque |
| 22 | `disabledSecondaryVariant` | `#F2F2F2` | opaque | `#404040` | opaque |
| 23 | `disabledOnSecondaryVariant` | `#B2B2B2` | opaque | `#707170` | opaque |
| 24 | `secondaryContainer` | `#F0F0F0` | opaque | `#434343` | opaque |
| 25 | `onSecondaryContainer` | `#A9A9A9` | opaque | `#7C7C7C` | opaque |
| 26 | `secondaryContainerVariant` | `#F0F0F0` | opaque | `#4F4F4F` | opaque |
| 27 | `onSecondaryContainerVariant` | `#A8A8A8` | opaque | `#959595` | opaque |
| 28 | `tertiaryContainer` | `#EAF2FF` | opaque | `#2B3B54` | opaque |
| 29 | `onTertiaryContainer` | `#3482FF` | opaque | `#4788FF` | opaque |
| 30 | `tertiaryContainerVariant` | `#EAF2FF` | opaque | `#505050` | opaque |
| 31 | `background` | `#FFFFFF` | opaque | `#242424` | opaque |
| 32 | `onBackground` | `#000000` | opaque | `#FFFFFF` | **alpha E6 = 90%** |
| 33 | `onBackgroundVariant` | `#8C93B0` | opaque | `#787E96` | opaque |
| 34 | `surface` | `#F7F7F7` | opaque | `#000000` | opaque |
| 35 | `onSurface` | `#000000` | opaque | `#F2F2F2` | opaque |
| 36 | `surfaceVariant` | `#FFFFFF` | opaque | `#242424` | opaque |
| 37 | `onSurfaceSecondary` | `#000000` | **alpha CC = 80%** | `#FFFFFF` | **alpha CC = 80%** |
| 38 | `onSurfaceVariantSummary` | `#000000` | **alpha 99 = 60%** | `#FFFFFF` | **alpha 80 = 50%** |
| 39 | `onSurfaceVariantActions` | `#000000` | **alpha 66 = 40%** | `#FFFFFF` | **alpha 66 = 40%** |
| 40 | `disabledOnSurface` | `#B2B2B2` | opaque | `#666666` | opaque |
| 41 | `surfaceContainer` | `#FFFFFF` | opaque | `#242424` | opaque |
| 42 | `onSurfaceContainer` | `#000000` | opaque | `#FFFFFF` | **alpha E6 = 90%** |
| 43 | `onSurfaceContainerVariant` | `#959595` | opaque | `#737373` | opaque |
| 44 | `surfaceContainerHigh` | `#E8E8E8` | opaque | `#242424` | opaque |
| 45 | `onSurfaceContainerHigh` | `#A2A2A2` | opaque | `#666666` | opaque |
| 46 | `surfaceContainerHighest` | `#E8E8E8` | opaque | `#2D2D2D` | opaque |
| 47 | `onSurfaceContainerHighest` | `#000000` | opaque | `#E9E9E9` | opaque |
| 48 | `outline` | `#D9D9D9` | opaque | `#404040` | opaque |
| 49 | `dividerLine` | `#E0E0E0` | opaque | `#393939` | opaque |
| 50 | `windowDimming` | `#000000` | **alpha 4D ≈ 30%** | `#000000` | **alpha 99 = 60%** |
| 51 | `sliderKeyPoint` | `#A3B3CD` | **alpha 4D ≈ 30%** | `#7A8AA6` | **alpha 4D ≈ 30%** |
| 52 | `sliderKeyPointForeground` | `#6EB5FF` | opaque | `#5DAAFF` | opaque |
| 53 | `sliderBackground` | `#000000` | **alpha 0F ≈ 6%** | `#FFFFFF` | **alpha 26 ≈ 15%** |

> 共 53 个 token（源码 `Colors` 类构造参数 54 个，其中 `onSecondaryVariant` 出现两次为笔误重复，
> 实际唯一 token 53 个）。原文中 `tertiaryContainer` 无对应的 `tertiary` / `onTertiary`
> （Miuix 未定义），仅有 `tertiaryContainer` / `onTertiaryContainer` / `tertiaryContainerVariant` 三个。

### 关键 token 的组件归属（源码 Javadoc 明确标注）
- `primary` / `onPrimary`：**Switch、Button、Slider**
- `primaryVariant`：**Card**
- `disabledPrimary` / `disabledOnPrimary`：开关禁用态
- `disabledPrimaryButton` / `disabledOnPrimaryButton`：按钮禁用态
- `disabledPrimarySlider`：滑块禁用态
- `windowDimming`：Dialog、Dropdown、Spinner、BottomSheet 遮罩

### 组件默认取色（源码抄录）
| 组件 | 属性 | 取值 |
|---|---|---|
| Card | color / contentColor | `surfaceContainer` / `onSurfaceContainer` |
| Button（默认） | color / contentColor | `secondaryVariant` / `onSecondaryVariant` |
| Button（禁用） | disabledColor / disabledContentColor | `disabledSecondaryVariant` / `disabledOnSecondaryVariant` |
| Button（primary 变体） | color / contentColor | `primary` / `onPrimary` |
| Button（primary 禁用） | disabledColor / disabledContentColor | `disabledPrimaryButton` / `disabledOnPrimaryButton` |
| Switch | checkedThumbColor / uncheckedThumbColor | `onPrimary` / `onSecondary` |
| Switch | checkedTrackColor / uncheckedTrackColor | `primary` / `secondary` |
| Switch（禁用未选中） | thumb / track | `disabledOnSecondary` / `disabledSecondary` |
| Slider | foregroundColor | `primary` |
| Slider | backgroundColor | `sliderBackground` |
| Slider | thumbColor | `onPrimary` |
| Slider | keyPointColor / keyPointForegroundColor | `sliderKeyPoint` / `sliderKeyPointForeground` |
| Slider（禁用） | foreground / background / thumb | `disabledPrimarySlider` / `disabledSecondary` / `disabledOnPrimary` |
| TopAppBar | container / title / largeTitle / subtitle | `surface` / `onSurface` / `onSurface` / `onSurfaceVariantSummary` |

---

# 2. 文本样式表（14 个样式）

来源：`TextStyles.kt` L146–L230，文档表 https://compose-miuix-ui.github.io/miuix/zh_CN/guide/textstyles （两者逐字一致）。

| 样式名 | 字号 | 字重 | 行高 | 字间距 |
|---|---|---|---|---|
| `main` | 17sp | Normal (400) | 未设置（字体自然行高） | 未设置 |
| `paragraph` | 17sp | Normal (400) | **1.2em** | 未设置 |
| `body1` | 16sp | Normal (400) | 未设置 | 未设置 |
| `body2` | 14sp | Normal (400) | 未设置 | 未设置 |
| `button` | 17sp | Normal (400) | 未设置 | 未设置 |
| `footnote1` | 13sp | Normal (400) | 未设置 | 未设置 |
| `footnote2` | 11sp | Normal (400) | 未设置 | 未设置 |
| `headline1` | 17sp | Normal (400) | 未设置 | 未设置 |
| `headline2` | 16sp | Normal (400) | 未设置 | 未设置 |
| `subtitle` | 14sp | **Bold (700)** | 未设置 | 未设置 |
| `title1` | 32sp | Normal (400) | 未设置 | 未设置 |
| `title2` | 24sp | Normal (400) | 未设置 | 未设置 |
| `title3` | 20sp | Normal (400) | 未设置 | 未设置 |
| `title4` | 18sp | Normal (400) | 未设置 | 未设置 |

**要点**
- 全部 14 个样式中，**只有 `subtitle` 设置了 `fontWeight = FontWeight.Bold`**，其余均为默认 Normal。
- **只有 `paragraph` 设置了 `lineHeight = 1.2f.em`**，其余无行高。
- **字间距（letterSpacing）全部未设置**，即使用平台/字体默认值。
- 没有 `caption` 样式；最接近的是 `footnote2` (11sp)。
- 官方字体为 **MiSans VF**（文档站点加载 `cdn-font.hyperos.mi.com/font/css?family=MiSans_VF`）。

### sp → px 换算
- 1sp = 1dp @ 默认字体缩放。桌面 1x（96 DPI）下 **1dp = 1px = 1 QSS px**。
- Qt 侧建议统一用 `QFont.setPixelSize()`；若用 `setPointSizeF()` 需按 `px = pt × DPI/72` 反算
  （96 DPI 时 `pt = px × 0.75`），易引入 DPI 误差。

---

# 3. 组件视觉规格汇总

数值全部来自源码常量对象（`*Defaults`），括号内为源文件。

## 3.1 圆角半径
| 组件 | 圆角 | 来源 |
|---|---|---|
| **Card** | **16dp** | `CardDefaults.CornerRadius` (Card.kt) |
| **Button / TextButton** | **16dp** | `ButtonDefaults.CornerRadius` (Button.kt) |
| IconButton | 40dp | `IconButtonDefaults.CornerRadius` |
| TextField | 16dp | `TextFieldDefaults.CornerRadius` |
| TabRow（标准 / 带轮廓） | 12dp / 8dp | `TabRowDefaults` |
| Snackbar | 16dp（操作胶囊 50dp） | `SnackbarDefaults` |
| FloatingToolbar | 50dp | `FloatingToolbarDefaults.CornerRadius` |
| NavigationBar（浮动） | 50dp（= FloatingToolbarDefaults.CornerRadius） | NavigationBar.kt L141 |
| NavigationRail 选中项 | 16dp | `ExpandedItemCornerRadius` |
| Tooltip（plain / rich / 操作按钮） | 12dp / 16dp / 8dp | `TooltipDefaults` |
| OverlayBottomSheet | **28dp** | overlaybottomsheet.md |
| ColorPalette | 16dp（指示器半径 10dp） | colorpalette.md |
| ProgressIndicator | 胶囊（`CircleShape`） | ProgressIndicator.kt |
| Switch / Slider / Checkbox / RadioButton | `CircleShape`（胶囊/正圆） | 各自源文件 |

## 3.2 按钮
| 项 | 值 | 来源 |
|---|---|---|
| 最小宽度 | **58dp** | `ButtonDefaults.MinWidth` |
| 最小高度 | **40dp** | `ButtonDefaults.MinHeight` |
| 圆角 | **16dp** | `ButtonDefaults.CornerRadius` |
| 内边距 | `horizontal = 16dp, vertical = 13dp` | `ButtonDefaults.InsideMargin` |
| IconButton 最小宽/高/圆角 | 40dp / 40dp / 40dp | `IconButtonDefaults` |
| FloatingActionButton 最小宽/高 | 60dp / 60dp（展开 65dp） | `FloatingActionButtonDefaults` |
| FAB 阴影 | 4dp | 同上 |

## 3.3 Switch（开关）
| 项 | 值 | 来源 |
|---|---|---|
| **轨道尺寸** | **49dp × 28dp** | Switch.kt L143 `Modifier.size(49.dp, 28.dp)` |
| 轨道形状 | `CircleShape`（胶囊，radius = 14dp） | L144 |
| **滑块（thumb）直径** | **20dp** | L156 `.size(20.dp)` |
| 滑块未选中偏移 | **4dp** | L92 `targetValue = 4.dp` |
| 滑块选中偏移 | **25dp** | L92 `targetValue = 25.dp` |
| 滑块行程 | 21dp | 25 − 4 |
| 按压/悬停滑块缩放 | **×1.127** | L105 `1.127f` |
| 拖动范围钳制 | −21f ~ 0f（选中）/ 0f ~ 21f（未选中） | L178–L182 |
| 滑块位移动画 | `spring(dampingRatio = 0.7f, stiffness = 987f)` | L87 |
| 缩放动画 | `spring(dampingRatio = 0.6f, stiffness = 987f)` | L88 |
| 轨道颜色动画 | `spring(dampingRatio = 0.99f, stiffness = 438.6f)` | L113 |

## 3.4 Slider（滑块）
| 项 | 值 | 来源 |
|---|---|---|
| **整体高度（= 轨道粗细）** | **28dp** | `SliderDefaults.MinHeight` (Slider.kt L1352) |
| 轨道形状 | `CircleShape` 胶囊 + `StrokeCap.Round` | L846, L907 |
| 前景/背景绘制 | `drawLine(strokeWidth = barHeight)`，strokeWidth = 28dp | L902–L907 |
| **滑块（thumb）半径** | `barHeight / 2 × 0.72` = **14 × 0.72 = 10.08dp**（直径 **20.16dp**） | L923 |
| **关键点半径（常量）** | `SliderDefaults.KeyPointRadius` = **3.855dp** | L1357 |
| 关键点绘制半径（Slider 内） | `barHeight / 7.5` = **3.733dp** | L873, L907 |
| 拖动时轨道叠加 | 黑色、alpha **0.044**，`tween(150ms)` | L838–L842 |
| 触摸命中半径 | `knobRadius + thumbRadius × 0.5` | L185 |
| 垂直滑块宽度 | = MinHeight = 28dp | slider.md L116 |

> **形态关键**：Miuix 滑块的「轨道」是一根 **28dp 粗的胶囊**，thumb 是**画在胶囊内部的 ~20dp 圆**，
> 而不是常见的「细轨道 + 外部大圆点」。这是与 Material 最大的形态差异。

## 3.5 TopAppBar
| 项 | 值 | 来源 |
|---|---|---|
| **折叠高度** | **52dp** | `TopAppBarDefaults.CollapsedHeight` (L409) |
| SmallTopAppBar 垂直中心高度 | 50dp | `SmallTopAppBarCenterHeight` (L412) |
| **标题水平内边距** | **26dp** | `TitlePadding` (L400) |
| 导航图标起始边距 | 16dp | `NavigationIconPadding` (L403) |
| 操作图标末尾边距 | 16dp | `ActionIconPadding` (L406) |
| 无副标题时大标题底部边距 | 4dp | `LargeTitleBottomPadding` (L415) |
| 副标题底部边距 | 8dp | `SubtitleBottomPadding` (L418) |
| 容器底色 | `surface` | TopAppBar.kt L103 |
| 标题色 | `onSurface` | L104 |
| 大标题色 | `onSurface` | L106 |
| 副标题色 | `onSurfaceVariantSummary` | L108 |
| 吸附动画 | `spring(stiffness = 2500f)` | topappbar.md L208 |
| 滑动衰减 | `rememberSplineBasedDecay()` | topappbar.md L209 |

## 3.6 NavigationBar
### 标准 NavigationBar
| 项 | 值 | 来源 |
|---|---|---|
| **项目高度** | **64dp** | `NavigationBarDefaults.ItemHeight` (L442) |
| 图标尺寸 | 26dp | `IconSize` (L445) |
| 标签字号 | 12sp | `LabelFontSize` (L448) |
| 图标顶部内边距 | 8dp | `IconTopPadding` (L451) |
| 标签底部内边距 | 8dp | `BottomPadding` (L454) |
| 选中项按压 alpha | 0.5f | L457 |
| 未选中项按压 alpha | 0.6f | L460 |
| 未选中项常驻 alpha | **0.4f** | `UnselectedAlpha` (L463) |
| 项内最小高度 | 52dp | L315 `defaultMinSize(minHeight = 52.dp)` |
| 切换动画 | `tween(durationMillis = 300)` | L87, L207 |

### FloatingNavigationBar（浮动导航栏）
| 项 | 值 | 来源 |
|---|---|---|
| **外部水平边距** | **36dp**（有底部 padding 时 = 26dp + navBarBottomPadding） | L512, L293 |
| 阴影高度 | 1dp | L515 |
| 内部水平内边距 | 12dp | L518 |
| 项目间距 | 12dp | L521 |
| 图标尺寸 | 28dp | L524 |
| 图标周围内边距 | 10dp | L527 |

## 3.7 列表项 / 分组
| 项 | 值 | 来源 |
|---|---|---|
| **列表项最小高度** | **56dp** | Component.kt L161 `.heightIn(min = 56.dp)` |
| 列表项内边距 | `PaddingValues(16dp)` | `ComponentDefaults.InsideMargin` (L266) |
| 起始/居中内容间距 | **8dp** | L255 `Spacer(Modifier.height(8.dp))` |
| SmallTitle 内边距 | `PaddingValues(28dp, 8dp)` | smalltitle.md L64 |
| ScrollBar 圆角半径 | 10dp，alpha 0.2f | NavigationBar.kt L340 |

> **分组卡片间距**：Miuix 没有集中式 `Dimens` 对象（源码中不存在该文件），间距由调用方决定。
> 官方示例统一为：**卡片之间 16dp**、**卡片内元素之间 8dp**
> （card.md L98 `Spacer(Modifier.height(8.dp))`、L102 `Spacer(Modifier.height(16.dp))`）。

## 3.8 页面边距
| 项 | 值 | 来源 |
|---|---|---|
| **页面左右边距** | **26dp**（与 TopAppBar TitlePadding 对齐） | scaffold.md L40/L163/L198/L219：`.padding(top = paddingValues.calculateTopPadding(), start = 26.dp)` |
| Scaffold 自身 | **不施加**内容 padding，仅传递 window insets | Scaffold.kt L156–L181 |

## 3.9 图标尺寸
| 场景 | 尺寸 | 来源 |
|---|---|---|
| **默认图标尺寸**（painter 无固有尺寸时回退） | **24dp** | Icon.kt L204 `DefaultIconSizeModifier = Modifier.size(24.dp)` |
| NavigationBar 图标 | 26dp | NavigationBar.kt L445 |
| FloatingNavigationBar 图标 | 28dp | L524 |
| NavigationRail 图标 | 28dp | navigationrail.md L122 |
| Button 内 ProgressIndicator | 20dp（strokeWidth 4dp） | button.md L184–186 |
| Badge（仅图标 / 带内容） | 6dp / 16dp | `BadgeDefaults.Size` / `LargeSize` |

## 3.10 其余组件规格（速查）
| 组件 | 规格 | 来源 |
|---|---|---|
| **Divider 厚度** | **0.75dp** | `DividerDefaults.Thickness` (Divider.kt L71) |
| Checkbox 尺寸 | 26dp（`requiredSize`，`CircleShape`） | Checkbox.kt L173/L180 |
| RadioButton 尺寸 | 26dp（`requiredSize`，`CircleShape`） | RadioButton.kt L121/L128 |
| ProgressIndicator 线性高度 | 6dp | `DefaultLinearProgressIndicatorHeight` |
| ProgressIndicator 环形 | stroke 4dp，size 30dp | `DefaultCircularProgressIndicator*` |
| ProgressIndicator 无限指示器 | stroke 2dp，环绕点 2dp，size 20dp | `DefaultInfiniteProgressIndicator*` |
| TabRow 高度 | 42dp（带轮廓 45dp） | `TabRowHeight` / `TabRowWithContourHeight` |
| TabRow 项宽 | 最小 76dp / 最大 98dp（带轮廓 62dp / 84dp） | `TabRowMinWidth` / `TabRowMaxWidth` |
| TabRow 项间距 | 9dp（带轮廓 5dp） | tabrow.md L74/L93 |
| TextField | 圆角 16dp，内边距 `DpSize(16dp, 16dp)` | `TextFieldDefaults` |
| SearchBar | 内边距 `DpSize(12dp, 0dp)`，输入框最小高 45dp，输入字号 17sp | `SearchBarDefaults` |
| SearchBar 前置图标 | start 16dp / end 8dp | `LeadingIcon*Padding` |
| SearchBar 后置图标 | start 8dp / end 16dp | `TrailingIcon*Padding` |
| Snackbar | 圆角 16dp，内边距 all 12dp，外边距 start/end 12dp + top 8dp，操作胶囊圆角 50dp | `SnackbarDefaults` |
| Tooltip | 与锚点间距 8dp；plain 最大宽 200dp / 圆角 12dp / 内边距 h12 v8；rich 最大宽 320dp / 圆角 16dp / 内边距 16dp；caret `DpSize(16dp, 8dp)` | `TooltipDefaults` |
| BreadcrumbBar | 内边距 h12 v8，项高 32dp，项水平内边距 10dp，项最大宽 160dp | `BreadcrumbBarDefaults` |
| OverlayDialog | 外边距 `DpSize(20dp, 20dp)`，内边距 `DpSize(30dp, 30dp)` | overlaydialog.md L123–124 |
| OverlayBottomSheet | 圆角 28dp，最大宽 640dp，外边距 `DpSize(16dp, 0dp)`，内边距 `DpSize(32dp, 16dp)` | overlaybottomsheet.md |
| ListPopup / 级联弹窗 | 最小宽度 200dp | overlaylistpopup.md L100 |
| FloatingToolbar | 圆角 50dp，外边距 `PaddingValues(12dp, 8dp)`，阴影 4dp | `FloatingToolbarDefaults` |
| PullToRefresh | 指示圈 20dp；文本 `fontSize = 14sp, fontWeight = Bold` | `PullToRefreshDefaults` |
| NavigationRail | 展开宽 240dp，垂直内边距 24dp，头部间距 24dp，图标 28dp，图标文字间距 4dp，项垂直内边距 12dp，标签 12sp / 展开 16sp，展开项水平外边距 12dp，展开项圆角 16dp，收起指示器垂直内边距 4dp，展开项内容内边距 h14 v14，展开项图标文字间距 16dp | navigationrail.md L119–132 |

---

# 4. 关键组件形态描述

> Miuix 文档不含静态截图；下方「预览」为官方**实时 Compose-Wasm demo**（已验 HTTP 200）。

## 4.1 Card
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/card
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=card

- 基础容器组件，用于承载相关内容和操作；分**静态**与**交互式**两种模式。源文件 Card.kt。
- **圆角 16dp**，使用 `squircleSurface`（超椭圆平滑圆角），**不是**普通 `RoundedCornerShape`。
- 默认底色 `surfaceContainer`（Light `#FFFFFF` / Dark `#242424`），内容色 `onSurfaceContainer`
  （Light `#000000` / Dark 90% 白）。
- `InsideMargin` 默认 `PaddingValues(0.dp)` —— **卡片自身不带内边距**，
  内容边距完全由调用方通过 `insideMargin` 传入（官方示例普遍用 16dp）。
- 交互式卡片可开启 `pressFeedbackType`、`showIndication`、`holdDownState`、`onClick`、`onLongPress`。
- 形态特征：白色/深灰实心圆角块，**无边框、无阴影**，靠底色与页面 `surface`
  （Light `#F7F7F7` / Dark `#000000`）的明度差区分层次。

## 4.2 Button
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/button
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=button

- **最小尺寸 58dp × 40dp**，**圆角 16dp**（squircle），内边距水平 16dp / 垂直 13dp。源文件 Button.kt。
- 默认（次要）按钮：底色 `secondaryVariant`（Light `#F0F0F0` / Dark `#434343`），
  文字 `onSecondaryVariant`（Light `#303030` / Dark `#D9D9D9`）。
- `buttonColorsPrimary` 变体：底色 `primary`（Light `#3482FF` / Dark `#277AF7`），文字 `onPrimary`（白）。
- 禁用态：次要 → `disabledSecondaryVariant` / `disabledOnSecondaryVariant`；
  primary → `disabledPrimaryButton` / `disabledOnPrimaryButton`。
- 文字样式为 `button`：**17sp / Normal**。
- 可内嵌 `ProgressIndicator(size = 20dp, strokeWidth = 4dp)` 表示加载态。
- 衍生的 `TextButton` 共用同一套尺寸与圆角。
- 形态特征：**圆角矩形而非全圆角胶囊**（16dp 圆角对 40dp 高度占比很大，但仍保留直边）。

## 4.3 Switch
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/switch
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=switch

- **胶囊轨道 49dp × 28dp**，`CircleShape` 裁剪，`drawRect` 填充底色。源文件 Switch.kt。
- **圆形滑块直径 20dp**，垂直居中，水平偏移：未选中 **4dp** → 选中 **25dp**
  （行程 21dp，两端各留 4dp 边距）。
- 选中：轨道 `primary`，滑块 `onPrimary`（白）。
  未选中：轨道 `secondary`（Light `#E6E6E6` / Dark `#505050`），滑块 `onSecondary`（白）。
- 禁用未选中：轨道 `disabledSecondary`，滑块 `disabledOnSecondary`。
- 交互：按下/悬停/拖动时滑块**放大到 1.127 倍**；支持**横向拖拽切换**（非仅点击），
  拖拽位移除以 2 做阻尼，并带分段触感反馈。
- 动画：滑块位移 `spring(0.7, 987)`，缩放 `spring(0.6, 987)`，轨道配色 `spring(0.99, 438.6)`。
- 形态特征：比 Material 3 的 Switch **更扁更宽**（49×28 vs 52×32），滑块相对轨道更大（20/28 ≈ 71%）。

## 4.4 TopAppBar
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/topappbar
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=topappbar

- 三种布局：**SmallTopAppBar**（垂直中心高 50dp）、**TopAppBar**（标准）、
  **LargeTopAppBar**（含大标题 + 可选副标题）。源文件 TopAppBar.kt。
- **折叠高度 52dp**；标题水平内边距 **26dp**；导航图标起始 16dp；操作图标末尾 16dp。
- 大标题底部内边距 4dp（无副标题时）；副标题底部内边距 8dp（大小标题均适用）。
- 底色 `surface`；标题/大标题 `onSurface`；副标题 `onSurfaceVariantSummary`
  （Light 60% 黑 / Dark 50% 白）。
- 滚动时大标题收起并**吸附**：`spring(stiffness = 2500f)`，衰减用 `rememberSplineBasedDecay()`。
- 形态特征：**大标题字号很大 + 扁平无阴影**，靠底色与页面 `surface` 的明度带做分隔。

## 4.5 NavigationBar
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/navigationbar
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=navigationbar

- 两种模式：**标准 NavigationBar** 与 **FloatingNavigationBar**（浮动）。源文件 NavigationBar.kt。
- 标准：**项目高度 64dp**，图标 **26dp**，标签 **12sp**，图标顶部内边距 8dp，标签底部内边距 8dp；
  项内最小高度 52dp；选中/未选中按压 alpha 0.5 / 0.6；未选中常驻 alpha **0.4**。
- 显示模式 `NavigationBarDisplayMode.IconAndText`（默认，图标 + 文字）。
- 浮动：圆角 **50dp**（胶囊），外部水平边距 **36dp**，内部水平内边距 12dp，
  项间距 12dp，图标 **28dp**，图标周围内边距 10dp，阴影高度 **1dp**。
- 切换动画统一 `tween(300ms)`。
- 形态特征：**iOS 风格底部标签栏** —— 图标在上、小字在下，未选中项明显变淡（40% 不透明度）；
  浮动版是一个悬浮胶囊条，两侧各留 36dp。

## 4.6 Slider
文档：https://compose-miuix-ui.github.io/miuix/zh_CN/components/slider
预览：https://compose-miuix-ui.github.io/miuix/compose/index.html?id=slider

- **高度 28dp，轨道即整根 28dp 粗的胶囊**（圆头 `StrokeCap.Round`），
  前景（已选）`primary`，背景 `sliderBackground`（Light 6% 黑 / Dark 15% 白）。源文件 Slider.kt。
- **滑块是画在胶囊内部的圆，半径 10.08dp（直径 20.16dp）**，颜色 `onPrimary`（白）。
- 可选**关键点（key points）**：半径 `3.855dp`，未选中 `sliderKeyPoint`（30% 透明度），
  已选 `sliderKeyPointForeground`（Light `#6EB5FF` / Dark `#5DAAFF`）。
- 拖动时轨道叠加一层黑色 **alpha 0.044**（`tween(150ms)`）。
- 支持垂直方向、范围滑块（`RangeSlider`，双滑块）、反向方向、`keyPoints`、`stepFractions`。
- 禁用：前景 `disabledPrimarySlider`，背景 `disabledSecondary`，滑块 `disabledOnPrimary`。
- 触感反馈 `SliderHapticEffect.Edge`（默认，0% 与 100% 触发）。
- 形态特征：**外观像一根粗色条内嵌一个圆点** —— 与 Material 3 的「细轨道 + 外部大圆」完全不同，
  这是复刻时最容易被忽略、也最影响观感的差异点。

---

# 5. Squircle（超椭圆平滑圆角）规格

来源：https://compose-miuix-ui.github.io/miuix/zh_CN/guide/squircle 与 `SquirclePath.kt`。

## 5.1 官方参数
| 参数 | 值 | 说明 | 来源 |
|---|---|---|---|
| `SquircleDefaults.Extension` | **1.1f** | 角部区域大小相对 `cornerRadius` 的倍数；`1.0` = 标准圆弧 | SquirclePath.kt L20 |
| `ExtensionMin` | 1.0f | 下限 | L23 |
| `ExtensionMax` | 2.0f | 上限 | L26 |
| `SQUIRCLE_CONTROL` | **0.643f** | 三次贝塞尔控制柄比例（internal） | L35 |
| SDF 位图尺寸 | 512 | `BakeSquircleSdfTask.size` | miuix-squircle/build.gradle.kts |
| SDF halfRange | 0.125f | 距离场半程（抗锯齿过渡带） | build.gradle.kts |
| SDF 贝塞尔采样数 | 64 | 距离场求最近点的采样密度 | build.gradle.kts |
| 圆形混合阈值 | **π/4 ≈ 0.7853982** | `BLEND_THRESHOLD_RATIO`：超过该 `cornerSize/halfMin` 比例时与正圆 SDF 混合，使胶囊/正圆干净退化 | SquircleBackground.kt |

## 5.2 官方原文（形态说明）
> 「`RoundedCornerShape` 的圆角是一段纯粹的四分之一圆弧，直线段与弧之间的曲率存在突变。
> squircle 把曲率分布到更宽的角部区域，呈现现代移动端图标常见的『连续曲率圆角』观感。
> 视觉差异在中到大半径时最明显。」

> 「`extension` 决定连续曲率区从顶点延伸出去的距离。`1.0` 等同标准圆弧；默认 `1.1` 给出标准的 squircle 观感。」

## 5.3 精确路径算法（可直接翻译成 Qt）
~~~
tile   = min(cornerRadius × 1.1, min(width, height) / 2)
handle = tile × (1 − 0.643) = tile × 0.357

moveTo(tile, 0)
lineTo(width − tile, 0)
cubicTo(width − handle, 0,        width, handle,         width, tile)
lineTo(width, height − tile)
cubicTo(width, height − handle,   width − handle, height, width − tile, height)
lineTo(tile, height)
cubicTo(handle, height,           0, height − handle,    0, height − tile)
lineTo(0, tile)
cubicTo(0, handle,                handle, 0,            tile, 0)
close()
~~~
与 `QPainterPath::arcTo` 的四分之一圆弧相比，区别仅在**曲线起点从 `r` 外推到了 `1.1r`**，
且控制柄长度固定为 `0.357 × tile`。

## 5.4 提供的 Modifier / API
| API | 行为 | 回退 |
|---|---|---|
| `squircleBackground(color, cornerRadius, extension)` | 仅填充，**不裁剪**子内容 | `Modifier.background(color, RoundedCornerShape(r))` |
| `squircleSurface(color, cornerRadius, extension)` | 填充 + 裁剪（同一离屏 layer） | `clip(RoundedCornerShape(r)).background(color)` |
| `squircleClip(cornerRadius, extension)` | 仅裁剪 | `Modifier.clip(RoundedCornerShape(r))` |
| `squircleBorder(width, color, cornerRadius, extension)` | 仅描边，自动内缩半个描边宽；**基于 path，不需 shader** | 圆弧描边 |
| `absoluteSquircle*` | 同上，但接受物理方位角参数，不随 RTL 翻转 | — |
| `Path.addSquircleRect(width, height, cornerRadius, extension, squircleEnabled)` | 直接构造 path | `squircleEnabled = false` 时退化为圆角矩形 |

**平台下限**：shader 版 modifier 需 Android API 33+（更低版本自动回退，不崩溃）；
path 版在所有平台可用。全局开关 `LocalSquircleEnabled`（默认 `true`）。

---

# 6. Qt / PySide6 QSS 落地建议

## 6.1 Token → QSS 属性映射
| Miuix token | Qt 落地 | 说明 |
|---|---|---|
| `background` | `QWidget { background-color }`（顶层窗口/页面底） | Light `#FFFFFF` / Dark `#242424` |
| `surface` | Scaffold / TopAppBar / NavigationBar 的 `background-color` | Light `#F7F7F7` / Dark `#000000` |
| `surfaceContainer` | **Card** / 弹窗面板 `background-color` | Light `#FFFFFF` / Dark `#242424` |
| `surfaceContainerHigh` / `…Highest` | 悬浮层、次级面板、hover 态 | Light 均 `#E8E8E8`；Dark `#242424` / `#2D2D2D` |
| `surfaceVariant` | 输入框、次级容器底色 | Light `#FFFFFF` / Dark `#242424` |
| `primary` | `QPushButton[primary] { background-color }`、`QSlider::sub-page`、选中态 | Light `#3482FF` / Dark `#277AF7` |
| `onPrimary` | 上述按钮的 `color`、滑块 thumb 色 | 白 |
| `primaryVariant` | Card 强调变体底色 | Light `#3482FF` / Dark `#0073DD` |
| `secondaryVariant` | **默认按钮**底色 | Light `#F0F0F0` / Dark `#434343` |
| `onSecondaryVariant` | 默认按钮文字色 | Light `#303030` / Dark `#D9D9D9` |
| `secondary` | Switch 未选中轨道色 | Light `#E6E6E6` / Dark `#505050` |
| `tertiaryContainer` / `onTertiaryContainer` | 蓝色浅底标签/徽章 | Light `#EAF2FF` / `#3482FF`；Dark `#2B3B54` / `#4788FF` |
| `error` / `errorContainer` / `onErrorContainer` | 错误文字 / 错误底 / 错误底上文字 | Light `#E94634` / `#FDF6F4` / `#410002` |
| `onSurface` | 主文字 `color` | Light `#000000` / Dark `#F2F2F2` |
| `onSurfaceSecondary` (80%) | 次级文字 | `rgba(0,0,0,0.8)` / `rgba(255,255,255,0.8)` |
| `onSurfaceVariantSummary` (60%/50%) | 摘要/副标题文字 | `rgba(0,0,0,0.6)` / `rgba(255,255,255,0.5)` |
| `onSurfaceVariantActions` (40%) | 操作/提示文字 | `rgba(0,0,0,0.4)` / `rgba(255,255,255,0.4)` |
| `onSurfaceContainerVariant` | 卡片内次要文字 | Light `#959595` / Dark `#737373` |
| `disabledOnSurface` | 禁用文字 `color` | Light `#B2B2B2` / Dark `#666666` |
| `outline` | `border: 1px solid` | Light `#D9D9D9` / Dark `#404040` |
| `dividerLine` | `QFrame[role="divider"] { background-color; max-height: 1px }` | 源码厚度 **0.75dp**；Qt 画不出 0.75px 实线 → **用 1px 并把颜色调淡**，或开抗锯齿自绘 0.75px |
| `windowDimming` | `QWidget#overlay { background-color: rgba(0,0,0,0.3 / 0.6) }` | 遮罩层 |
| `sliderKeyPoint` / `…Foreground` | `QSlider::handle` 上的刻度点（需自绘） | 30% 透明度 |
| `sliderBackground` | `QSlider::groove:horizontal { background-color }` | Light `rgba(0,0,0,0.06)` / Dark `rgba(255,255,255,0.15)` |

## 6.2 尺寸映射（1dp = 1px @ 1x）
| 组件 | QSS |
|---|---|
| Card | `border-radius: 14px`（≈0.88×16，见 6.4）；`padding: 16px`（由 insideMargin 决定） |
| Button | `min-width: 58px; min-height: 40px; border-radius: 14px; padding: 13px 16px` |
| IconButton | `min-width/height: 40px; border-radius: 20px`（QSS 用半高近似正圆） |
| TextField | `min-height: 45px; border-radius: 14px; padding: 16px` |
| Switch | 自绘：`49×28`，`border-radius: 14px`，thumb `20×20` 圆 |
| Slider | 自绘：`height: 28px`，`QSlider::groove { border-radius: 14px }` |
| TopAppBar | `min-height: 52px; padding-left/right: 26px` |
| NavigationBar | `min-height: 64px`；图标 26px；标签 `font-size: 12px` |
| NavigationBar（浮动） | `margin: 0 36px; border-radius: 25px; padding: 0 12px` |
| List item | `min-height: 56px; padding: 16px` |
| 页面左右边距 | `padding-left/right: 26px` |
| 图标 | `width/height: 24px`（默认） |
| Divider | `max-height: 1px`（源码 0.75dp） |

## 6.3 字号映射
QSS 只有 `font-size`（px）和 `font-weight`，**不支持 line-height 和 letter-spacing**。
- 直接映射：`main` / `paragraph` / `button` / `headline1` = `17px`；`body1` / `headline2` = `16px`；
  `body2` / `subtitle` = `14px`；`footnote1` = `13px`；`footnote2` = `11px`；
  `title1` = `32px`；`title2` = `24px`；`title3` = `20px`；`title4` = `18px`。
- `subtitle` 额外加 `font-weight: 700`；其余**不要加粗**（`font-weight: 400`）。
- **行高**：只有 `paragraph` 需要 1.2em。QSS 无 `line-height`，需用
  `QLabel` + 富文本 `<div style="line-height:120%">`，或在 `paintEvent` 里用
  `QTextDocument` + `QTextBlockFormat.setLineHeight(120, ProportionalHeight)`。
- **字间距**：Miuix 全部未设置，Qt 侧**保持默认**即可（不要主动加 `letter-spacing`）。
- 字体：优先 **MiSans**（HyperOS 官方字体）；缺失时按
  `MiSans, "Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif` 回退。

## 6.4 squircle 在 Qt 里怎么近似
QSS 的 `border-radius` **只能画四分之一圆弧**（内部走 `QPainterPath.arcTo`），没有超椭圆能力。三个层次：

**方案 A（推荐，最忠实）：自绘 `QPainterPath`**
把 5.3 的算法一比一翻译过去 —— 这是**唯一能真正还原 squircle 的做法**，开销极低：
~~~python
# 伪代码，仅示意
tile = min(radius * 1.1, min(w, h) / 2)
handle = tile * (1.0 - 0.643)          # = tile * 0.357
p = QPainterPath()
p.moveTo(tile, 0)
p.lineTo(w - tile, 0)
p.cubicTo(w - handle, 0, w, handle, w, tile)
p.lineTo(w, h - tile)
p.cubicTo(w, h - handle, w - handle, h, w - tile, h)
p.lineTo(tile, h)
p.cubicTo(handle, h, 0, h - handle, 0, h - tile)
p.lineTo(0, tile)
p.cubicTo(0, handle, handle, 0, tile, 0)
p.closeSubpath()
~~~
配合 `QWidget.setMask()`、`QPainter.setClipPath()` 或 `QRegion` 即可实现圆角窗体/卡片/按钮。
这也是 Miuix `squircleBorder` 的做法（纯 path，不需 shader）。

**方案 B（纯 QSS，够用）：`border-radius` 取 0.9 倍**
用圆弧近似 squircle。以下推导为**我的几何计算，非官方数值**：
- squircle 角部曲线起点距角点 `1.1r × (1,0)`，控制柄长 `0.357 × 1.1r = 0.3927r`。
- 半径 `R` 的圆弧，标准贝塞尔逼近控制柄长 `= R × (1 − 0.5523) = 0.4477R`。
- **对齐控制柄长**：`0.4477R = 0.3927r` → `R ≈ 0.88r`。
- **对齐 45° 对角线内缩量**：squircle 为 `0.4027r`，圆弧为 `0.4142R` → `R ≈ 0.97r`。
- 取折中：**QSS `border-radius` ≈ 0.9 × Miuix 圆角**。

| Miuix 圆角 | QSS 近似 |
|---|---|
| 8dp（Button 示例、TabRow 带轮廓） | `7px` |
| 10dp（BreadcrumbBar 项） | `9px` |
| 12dp（TabRow 标准、Tooltip plain） | `11px` |
| **16dp（Card / Button / TextField / Snackbar / Tooltip rich）** | **`14px`** |
| 28dp（BottomSheet） | `25px` |
| 50dp（浮动导航栏 / FloatingToolbar / Snackbar 操作胶囊） | `45px`（或 `border-radius: 999px` 做胶囊，此时差异不可见） |

> 圆角 **≤ 12dp 时圆弧与 squircle 视觉差异极小**，方案 B 完全可用；
> **≥ 16dp 起差异可见**（Card、浮动导航栏最明显），建议对 Card / NavigationBar / BottomSheet
> 改用方案 A。

**方案 C（大圆角/胶囊）：直接退化**
当 `radius ≥ min(w,h)/2` 时，Miuix 本身就会把 squircle 与正圆混合
（`BLEND_THRESHOLD_RATIO = π/4 ≈ 0.7854`）。因此**胶囊形按钮、浮动导航栏（50dp 圆角 + 有限高度）**
直接用 QSS `border-radius: 999px` 或半高值即可，无需 squircle，视觉几乎无差。

**注意事项**
- QSS 中 `border-radius` 与 `border` 同时存在时，Qt 沿圆角裁剪边框，**不会**产生连续曲率；
  需要「描边 + squircle」时必须走方案 A（自绘 `QPainterPath` 后 `QPen` 描边，并内缩半个线宽 ——
  与 Miuix `squircleBorder` 的「自动内缩半个描边宽度」一致）。
- Qt 的 `border-radius` **不会**自动裁剪子控件内容，需对子控件单独设 mask/clip，
  或用 `QPainter.setClipPath(path, Qt.IntersectClip)`。
- 高 DPI（`QT_SCALE_FACTOR > 1`）下 QSS 的 px 是逻辑像素，与 dp 的 1:1 关系成立；
  但 `border-radius` 会被缩放，若追求极致可在 `paintEvent` 中按 `devicePixelRatio` 自绘。
- Miuix 的 `squircleSurface` 会把子内容裁进同一个离屏 layer；Qt 侧对复杂子树建议先用
  离屏 `QPixmap`/`QGraphicsEffect` 合成再一次裁剪，避免重复绘制。
