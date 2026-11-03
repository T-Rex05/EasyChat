"""数据可视化工具（fig_inter）

⛔ 安全警告 —— 接线前必读（2026-09-18 实测）
────────────────────────────────────────────────────────────────
本模块**当前未注册**到 Hermes 工具注册表（不在
`tools_decorator.get_project_tools()`；`registry.get_entry("fig_inter")` 实测为
None），其 `_toolset = "data"` 也已是废弃工具组。这是**有意的**，不要直接把它加回
`get_project_tools()`：

`_fig_inter_impl` 用 `exec(py_code, g, local_vars)` 执行 LLM 生成的代码，
沙箱只有一层受限 `__builtins__` 白名单，**没有任何 AST 检查**；而 `local_vars`
里暴露的是**真实模块对象** `plt` / `pd` / `sns` —— 模块对象自带 `__builtins__`，
白名单因此形同虚设。实测可完整逃逸：

    plt.__builtins__['__import__']('os').getcwd()   # → 成功返回项目目录

由此可 `('os').system(...)` 执行任意命令，且**绕开**终端主机白名单、命令黑名单、
exec 审批卡片，以及 code_executor 的 AST 检查（本路径根本没有这一层）。

如需恢复图表能力，正确顺序是：先加固沙箱（子进程 + 白名单 AST，禁止访问
`__builtins__`/模块对象，或改用受限渲染 DSL），再注册工具。
────────────────────────────────────────────────────────────────

移植自 eyes-agent 的 data_visualization 工具，适配 AgentForge 架构： — 让 LLM 用 matplotlib 生成统计图，供 PDF 报告插入。

移植自 eyes-agent 的 data_visualization 工具，适配 AgentForge 架构：
- 用 langchain @tool 装饰器（与 tools_decorator.py 现有工具一致）
- pandas / seaborn 改为可选依赖（未安装时设为 None，不影响纯 matplotlib 绘图）
- 输出目录：项目根 static/charts/，自动创建
"""
import os
import uuid
import threading
from datetime import datetime
from typing import Optional

import matplotlib
import matplotlib.figure
import matplotlib.pyplot as plt
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.utils.log_utils import log

logger = log

# 可选依赖：未安装则置 None，AI 代码引用时会报错但纯 plt 绘图不受影响
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    import seaborn as sns
except ImportError:
    sns = None

# 全局画图锁，防止并发线程操作 plt 全局状态导致图表丢失或混乱
_fig_lock = threading.Lock()

# 在模块加载时初始化字体配置（只执行一次）
_font_initialized = False

# 跨平台中文字体回退链：matplotlib 取列表中第一个「系统实际存在」的字体。
_CJK_FONTS = [
    "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Noto Sans CJK JP",
    "Arial Unicode MS", "Hiragino Sans GB", "Songti SC", "STHeiti",
    "Microsoft YaHei", "SimHei",
    "DejaVu Sans",
]


def _init_fonts():
    """初始化中文字体配置（每进程只执行一次）。

    依赖 matplotlib 自带的持久字体缓存（fontlist-*.json，~ms 级解析），
    绝不每进程强制 fontManager.__init__() 全盘重扫（独占 ~17s）。
    仅当缓存里确实没有任何中文字体时才做一次性重扫自愈。
    """
    global _font_initialized
    if _font_initialized:
        return

    plt.rcParams["font.sans-serif"] = _CJK_FONTS
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    try:
        from matplotlib.font_manager import fontManager
        available = {getattr(f, "name", None) for f in fontManager.ttflist}
        cjk_wanted = [n for n in _CJK_FONTS if n != "DejaVu Sans"]
        if not any(n in available for n in cjk_wanted):
            logger.warning("matplotlib 字体缓存未含中文字体，触发一次性全量重扫")
            fontManager.__init__()
    except Exception as e:
        logger.warning(f"字体初始化探测失败（不致命，继续绘图）: {e}")

    _font_initialized = True


def _force_reset_fonts():
    """重置 matplotlib rcParams 字体（防 AI 代码篡改字体设置）。"""
    plt.rcParams["font.sans-serif"] = _CJK_FONTS
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False


def _lock_font_settings():
    """锁定字体设置，防止 AI 代码修改（在保存图片前调用）。"""
    plt.rcParams["font.sans-serif"] = _CJK_FONTS
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        for ax in fig.axes:
            for text in ax.texts:
                text.set_fontfamily("sans-serif")
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontfamily("sans-serif")
            if ax.title:
                ax.title.set_fontfamily("sans-serif")
            if ax.xaxis.label:
                ax.xaxis.label.set_fontfamily("sans-serif")
            if ax.yaxis.label:
                ax.yaxis.label.set_fontfamily("sans-serif")


class FigCodeInput(BaseModel):
    py_code: str = Field(..., description="matplotlib Python 代码")
    fname: Optional[str] = Field(default="chart", description="图表文件名（可选，实际文件名自动加时间戳）")


FIG_INTER_DESCRIPTION = (
    "生成数据可视化统计图（matplotlib），用于在 PDF 报告中插入柱状图、饼图、折线图、趋势图等。\n\n"
    "用法：传入一段完整的 matplotlib Python 代码，工具会执行代码并自动保存生成的图片，"
    "返回 markdown 图片引用（如 ![图表](/static/charts/xxx.png)），把它内联到报告正文对应位置即可。\n\n"
    "规则：\n"
    "1. 必须用 plt.figure() 或 fig, ax = plt.subplots() 创建图对象\n"
    "2. 不要调用 plt.savefig()（工具会自动保存，调了会被忽略）\n"
    "3. 每张图最多 2 个子图（plt.subplots(1,2) 或 (2,1) 可以，(2,2) 不行）\n"
    "4. 中文字体已自动配置，直接用中文标签即可\n"
    "5. 数据请用代码内嵌（列表/字典），不要读文件\n"
    "6. 可用变量：plt、pd(pandas，可能为 None)、sns(seaborn，可能为 None)、fig、ax\n\n"
    "示例代码：\n"
    "```python\n"
    "labels = ['A', 'B', 'C']\n"
    "values = [10, 20, 15]\n"
    "fig, ax = plt.subplots()\n"
    "ax.bar(labels, values, color='#10b981')\n"
    "ax.set_title('示例柱状图')\n"
    "ax.set_ylabel('数值')\n"
    "```"
)


@tool(args_schema=FigCodeInput, description=FIG_INTER_DESCRIPTION)
def fig_inter(py_code: str, fname: Optional[str] = "chart") -> str:
    """生成数据可视化图表（matplotlib 代码执行 + 自动保存 PNG + 返回 markdown 图引用）。"""
    with _fig_lock:
        return _fig_inter_impl(py_code, fname)


def _fig_inter_impl(py_code: str, fname: Optional[str] = "chart") -> str:
    _init_fonts()

    # 安全检查：限制代码长度，防止恶意或失控代码
    if len(py_code) > 5000:
        return "❌ 代码过长（超过 5000 字符限制），请简化代码"

    current_backend = matplotlib.get_backend()
    matplotlib.use("Agg")

    local_vars = {"plt": plt, "pd": pd, "sns": sns, "fig": None, "ax": None}

    _force_reset_fonts()

    # 替换 plt.savefig 为空操作，AI 调用了也不会保存文件，也不会报错
    original_savefig = getattr(plt, "savefig", None)

    def _noop_savefig(*args, **kwargs):
        logger.warning("AI 代码调用了 plt.savefig()，已忽略（工具会自动保存所有 Figure）")

    plt.savefig = _noop_savefig

    # 输出目录：使用统一路径配置
    from backend.config.paths import get_charts_dir
    output_dir = str(get_charts_dir())
    os.makedirs(output_dir, exist_ok=True)

    try:
        try:
            # 安全沙箱：限制危险内建函数，防止文件系统/网络/shell 访问
            _safe_builtins = {
                "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "map": map, "filter": filter,
                "sorted": sorted, "reversed": reversed,
                "int": int, "float": float, "str": str, "bool": bool,
                "list": list, "dict": dict, "tuple": tuple, "set": set,
                "True": True, "False": False, "None": None,
                "isinstance": isinstance,
                "min": min, "max": max, "sum": sum,
                "abs": abs, "round": round, "pow": pow,
                "iter": iter, "next": next,
                "chr": chr, "ord": ord, "repr": repr,
                "print": lambda *a, **kw: None,  # print 静默忽略
            }
            g = {"__builtins__": _safe_builtins}
            exec(py_code, g, local_vars)
            g.update(local_vars)

            _force_reset_fonts()

            # 查找所有 Figure 对象
            figures = []
            for var_name, var_value in local_vars.items():
                if isinstance(var_value, matplotlib.figure.Figure):
                    figures.append(var_value)

            fignums = plt.get_fignums()
            for fignum in fignums:
                fig = plt.figure(fignum)
                if fig not in figures:
                    figures.append(fig)

            if not figures:
                error_hint = "❌ 未找到图对象。常见原因：\n"
                error_hint += "1. 使用了未创建的变量（如直接使用 ax 而非 fig, ax = plt.subplots()）\n"
                error_hint += "2. 代码中没有调用 plt.figure() 或 plt.subplots()\n\n"
                error_hint += "正确示例：\n- plt.figure() + plt.plot()\n- fig, ax = plt.subplots()"
                return error_hint

            # 子图数量硬限制：每张图最多 2 个子图
            for idx, fig in enumerate(figures):
                n_axes = len(fig.axes)
                if n_axes > 2:
                    return (
                        f"❌ 子图数量超限：第{idx + 1}张图包含 {n_axes} 个子图，超过硬限制 2 个。\n"
                        f"请将指标拆成多张图（每张≤2子图），或合并为综合对比图。\n"
                        f"示例：plt.subplots(1, 2) 或 plt.subplots(2, 1) 均可，plt.subplots(2, 2) 不行。"
                    )

            # 保存所有找到的图表
            saved_images = []
            for idx, fig in enumerate(figures):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                random_suffix = uuid.uuid4().hex[:6]
                image_filename = f"chart_{timestamp}_{random_suffix}_{idx}.png"
                filepath = os.path.join(output_dir, image_filename)
                web_path = f"/static/charts/{image_filename}"

                _lock_font_settings()

                try:
                    fig.savefig(filepath, bbox_inches="tight", dpi=150)
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath)
                        logger.info(f"图片保存成功: {filepath} (大小: {file_size} bytes)")
                        saved_images.append(web_path)
                    else:
                        logger.error(f"图片保存失败: {filepath} 不存在")
                        return f"❌ 图片生成失败：文件未能保存到 {filepath}"
                except Exception as e:
                    logger.error(f"保存图片时出错: {e}")
                    return f"❌ 图片生成失败：{str(e)}"

            if len(saved_images) == 0:
                return "❌ 图片生成失败：未找到保存的图片"
            elif len(saved_images) == 1:
                return f"图表已生成，就地内联到当前分析模块段落内：\n![图表]({saved_images[0]})"
            else:
                image_list = "\n".join([f"![图表{i + 1}]({path})" for i, path in enumerate(saved_images)])
                return (
                    f"已生成 {len(saved_images)} 张图表（每条为独立可内联的 markdown 图引用），"
                    f"把每张图分别就地内联到它对应的分析模块段落内：\n"
                    f"{image_list}"
                )
        finally:
            if original_savefig:
                plt.savefig = original_savefig

    except NameError as e:
        error_msg = str(e)
        if "'ax'" in error_msg or "'fig'" in error_msg:
            return f"❌ 执行失败：{e}\n\n提示：使用了未定义的变量。请确保使用 'fig, ax = plt.subplots()' 或 'fig = plt.figure()' 创建对象。"
        return f"❌ 执行失败：{e}"
    except Exception as e:
        error_msg = str(e)
        if "tz must be string or tzinfo subclass" in error_msg or "UnitData object" in error_msg:
            return f"❌ 执行失败：数据类型不匹配\n\n提示：时间轴数据可能格式不正确。建议：1. 检查时间数据是否为字符串格式 2. 使用 pd.to_datetime() 转换时间列 3. 或绘图时不使用时间格式，直接使用索引\n\n错误详情：{error_msg[:200]}"
        return f"❌ 执行失败：{error_msg}"
    finally:
        plt.close("all")
        matplotlib.use(current_backend)


fig_inter._toolset = "data"
