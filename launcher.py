#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
digiKey 爬虫统一启动器（GUI）
功能：
    1. 选择要启动的项目（analog / north-ic / bom-ai / digKey2）
    2. 在线修改每个项目的配置（account.properties + keywords.txt）
    3. 一键启动对应项目的爬虫脚本，并实时显示运行日志
使用 Tkinter（标准库），无需安装额外依赖。
"""

import os
import sys
import threading
import subprocess
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 项目根目录（launcher.py 所在目录）
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 项目定义
# ============================================================
# key: 项目名
#     dir      项目目录（相对根目录）
#     script   要启动的入口脚本（相对项目目录）
#     cwd      运行时的工作目录（相对项目目录，None 表示项目目录本身）
#     desc     项目说明
PROJECTS = {
    "analog": {
        "dir": "analog",
        "script": "main.py",
        "cwd": "analog",
        "desc": "Analog Devices 官网数据爬取（Playwright）",
    },
    "north-ic": {
        "dir": "north-ic",
        "script": "main.py",
        "cwd": "north-ic",
        "desc": "IC交易网(ic.net.cn) 数据爬取（Playwright）",
    },
    "bom-ai": {
        "dir": "bom-ai",
        "script": "main.py",
        "cwd": "bom-ai",
        "desc": "BOM.ai 云价格数据爬取（requests）",
    },
    "digKey2": {
        "dir": "digKey2",
        "script": "spider_v2.py",
        "cwd": "digKey2",
        "desc": "Digikey 现货数据爬取 V2（Playwright + CF 人工绕过）",
    },
}

# 每个项目入口脚本在运行时需要的 python
# analog / north-ic / bom-ai 使用各自 venv；digKey2 使用系统 python
def get_python(project_dir):
    """返回运行某项目应使用的 python 可执行文件路径"""
    venv_py = os.path.join(ROOT_DIR, project_dir, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable  # 兜底：使用当前 python


# ============================================================
# properties 文件读写
# ============================================================
def parse_properties(content):
    """
    解析 .properties 内容，返回 (entries, comments_lines)
    entries: 有序的 (key, value) 列表
    comments_lines: 保留的注释/空行行号集合（0 起始），用于保存时还原
    """
    entries = []
    comment_lines = []
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("!"):
            comment_lines.append(idx)
            continue
        # 拆分 key=value
        if "=" in stripped:
            key, value = stripped.split("=", 1)
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
        else:
            comment_lines.append(idx)
            continue
        entries.append((key.strip(), value.strip()))
    return entries, comment_lines


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("digiKey 爬虫启动器")
        self.root.geometry("980x680")
        self.root.minsize(860, 600)

        self.current_project = None
        self.current_props = []        # [(key, value), ...]
        self.current_comment_lines = []  # 原始注释行号（用于还原）
        self.current_keywords = []
        self.current_keywords_backup = ""

        self.process = None            # 当前运行子进程
        self._reader = None            # 输出读取线程
        self.prop_widgets = {}         # key -> StringVar

        self._build_ui()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 左侧：项目选择 + 启动按钮
        left = ttk.Frame(self.root, padding=(10, 10, 5, 10))
        left.grid(row=0, column=0, sticky="nsw")
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="选择项目", font=("Microsoft YaHei", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6))

        self.project_var = tk.StringVar(value="analog")
        self.project_btns = {}
        for name in PROJECTS:
            rb = ttk.Radiobutton(
                left, text=name, value=name, variable=self.project_var,
                command=self.on_project_change,
            )
            rb.grid(row=len(self.project_btns) + 1, column=0, sticky="w", pady=2)
            self.project_btns[name] = rb

        # 项目说明
        self.desc_label = ttk.Label(
            left, text="", wraplength=150, foreground="#666", font=("Microsoft YaHei", 9))
        self.desc_label.grid(row=len(PROJECTS) + 2, column=0, sticky="w", pady=(8, 0))

        # 运行按钮
        self.run_btn = ttk.Button(left, text="▶  启动爬虫", command=self.on_run)
        self.run_btn.grid(row=len(PROJECTS) + 3, column=0, sticky="ew", pady=(16, 4))

        self.stop_btn = ttk.Button(left, text="■  停止", command=self.on_stop, state="disabled")
        self.stop_btn.grid(row=len(PROJECTS) + 4, column=0, sticky="ew", pady=(0, 4))

        self.open_out_btn = ttk.Button(left, text="打开输出目录", command=self.on_open_output)
        self.open_out_btn.grid(row=len(PROJECTS) + 5, column=0, sticky="ew", pady=(0, 4))

        ttk.Label(left, text="", font=("Microsoft YaHei", 9)).grid(
            row=len(PROJECTS) + 6, column=0, sticky="w")

        # 右侧：Notebook（配置 + 日志）
        right = ttk.Frame(self.root, padding=(5, 10, 10, 10))
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Tab1: 属性配置
        self.props_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.props_tab, text="账号/参数配置")

        # Tab2: 关键字
        self.keywords_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.keywords_tab, text="关键字")

        # Tab3: 运行日志
        self.log_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.log_tab, text="运行日志")

        self._build_props_tab()
        self._build_keywords_tab()
        self._build_log_tab()

        # 加载默认项目
        self.on_project_change()

    def _build_props_tab(self):
        self.props_tab.columnconfigure(0, weight=1)
        self.props_tab.rowconfigure(0, weight=1)

        # 属性编辑区（动态生成行）
        self.props_frame = ttk.Frame(self.props_tab)
        self.props_frame.grid(row=0, column=0, sticky="nsew")
        self.props_frame.columnconfigure(0, weight=1)

        # 提示
        ttk.Label(
            self.props_tab,
            text="修改后需点击「保存配置」生效。密码等敏感字段请勿泄露。",
            foreground="#c00",
            font=("Microsoft YaHei", 9),
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.props_save_btn = ttk.Button(
            self.props_tab, text="保存配置", command=self.on_save_props)
        self.props_save_btn.grid(row=2, column=0, sticky="e", pady=(8, 0))

    def _build_keywords_tab(self):
        self.keywords_tab.columnconfigure(0, weight=1)
        self.keywords_tab.rowconfigure(1, weight=1)

        ttk.Label(
            self.keywords_tab,
            text="每行一个关键字（型号），保存后生效。",
            foreground="#666",
            font=("Microsoft YaHei", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.keywords_text = scrolledtext.ScrolledText(
            self.keywords_tab, wrap="none", font=("Consolas", 10))
        self.keywords_text.grid(row=1, column=0, sticky="nsew")

        self.keywords_save_btn = ttk.Button(
            self.keywords_tab, text="保存关键字", command=self.on_save_keywords)
        self.keywords_save_btn.grid(row=2, column=0, sticky="e", pady=(8, 0))

    def _build_log_tab(self):
        self.log_tab.columnconfigure(0, weight=1)
        self.log_tab.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            self.log_tab, wrap="none", font=("Consolas", 9), state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # 状态栏
        status_bar = ttk.Frame(self.log_tab)
        status_bar.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        status_bar.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_bar, text="就绪", foreground="#0066cc")
        self.status_label.grid(row=0, column=0, sticky="w")

    # ---------------- 项目切换 ----------------
    def on_project_change(self):
        name = self.project_var.get()
        if name == self.current_project:
            return
        self.current_project = name
        info = PROJECTS[name]

        self.desc_label.config(text=info["desc"])

        # 标记当前 Tab 未保存的修改
        self._discard_unsaved_guard = False

        # 加载属性
        self._load_props()
        # 加载关键字
        self._load_keywords()
        # 日志保留，不清空

    def _config_path(self, name):
        return os.path.join(ROOT_DIR, PROJECTS[name]["dir"], "config", "account.properties")

    def _keywords_path(self, name):
        return os.path.join(ROOT_DIR, PROJECTS[name]["dir"], "config", "keywords.txt")

    def _load_props(self):
        # 清空属性编辑区
        for child in self.props_frame.winfo_children():
            child.destroy()

        path = self._config_path(self.current_project)
        self.current_props = []
        self.current_comment_lines = []

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.current_props, self.current_comment_lines = parse_properties(content)
        else:
            content = ""

        # 动态生成 key 标签 + value 输入框
        self.prop_widgets = {}  # key -> (StringVar, widget)
        if not self.current_props:
            ttk.Label(
                self.props_frame, text="该项目无账号/参数配置文件。",
                foreground="#999", font=("Microsoft YaHei", 9),
            ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
            return

        for i, (key, value) in enumerate(self.current_props):
            # 去掉前缀（如 "north-ic.UserName" -> "UserName"）
            display_key = key.split(".", 1)[-1] if "." in key else key
            ttk.Label(self.props_frame, text=display_key, font=("Microsoft YaHei", 9)).grid(
                row=i, column=0, sticky="w", padx=(5, 8), pady=4)

            var = tk.StringVar(value=value)
            entry = ttk.Entry(self.props_frame, textvariable=var, width=50)
            entry.grid(row=i, column=1, sticky="ew", pady=4)
            self.props_frame.columnconfigure(1, weight=1)

            # 密码字段显示为 *
            if "password" in key.lower() or "pwd" in key.lower():
                entry.config(show="•")
            self.prop_widgets[key] = var

    def _load_keywords(self):
        path = self._keywords_path(self.current_project)
        self.current_keywords_backup = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.current_keywords_backup = f.read()

        self.keywords_text.delete("1.0", tk.END)
        self.keywords_text.insert("1.0", self.current_keywords_backup)

    # ---------------- 保存 ----------------
    def on_save_props(self):
        """把属性编辑区的值写回 account.properties，保留注释和顺序"""
        path = self._config_path(self.current_project)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            # 读取原始文件，按原顺序重建
            original_lines = []
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    original_lines = f.read().splitlines()

            # 构建 key->var 映射（仅当前项目）
            updated = {k: v.get() for k, v in self.prop_widgets.items()}

            # 逐行处理原始内容：保留注释/空行，替换属性值
            result_lines = []
            for line in original_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                    result_lines.append(line)
                    continue
                # 是键值行
                if "=" in stripped:
                    key, _ = stripped.split("=", 1)
                elif ":" in stripped:
                    key, _ = stripped.split(":", 1)
                else:
                    result_lines.append(line)
                    continue
                key = key.strip()
                if key in updated:
                    # 保留原缩进，替换值
                    indent = line[:len(line) - len(line.lstrip())]
                    result_lines.append(f"{indent}{key}={updated[key]}")
                else:
                    result_lines.append(line)

            content = "\n".join(result_lines) + ("\n" if result_lines else "")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            messagebox.showinfo("提示", "配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败：{e}")

    def on_save_keywords(self):
        path = self._keywords_path(self.current_project)
        content = self.keywords_text.get("1.0", tk.END)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("提示", "关键字已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存关键字失败：{e}")

    # ---------------- 运行 ----------------
    def on_run(self):
        if self.process is not None:
            messagebox.showwarning("提示", "已有项目正在运行，请先停止")
            return

        name = self.project_var.get()
        info = PROJECTS[name]
        script = info["script"]
        script_path = os.path.join(ROOT_DIR, info["dir"], script)
        cwd = os.path.join(ROOT_DIR, info["cwd"]) if info["cwd"] else ROOT_DIR

        if not os.path.exists(script_path):
            messagebox.showerror("错误", f"入口脚本不存在：{script_path}")
            return

        python = get_python(info["dir"])

        # 清空日志区
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        self.append_log(f"==== 正在启动 [{name}] ====")
        self.append_log(f"脚本: {script}")
        self.append_log(f"Python: {python}")
        self.append_log(f"目录: {cwd}")
        self.append_log("=" * 50)

        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text=f"运行中：{name} ...", foreground="#c00")

        self.process = subprocess.Popen(
            [python, script],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # 不预先指定文本编码，以字节流读取，逐行自适应解码（兼容 UTF-8 / GBK）
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        self._reader = threading.Thread(target=self._read_output, args=(name,), daemon=True)
        self._reader.start()

    def _decode_line(self, raw):
        """将一行字节解码为文本：优先 UTF-8，失败回退 GBK，再失败用 replace"""
        for enc in ("utf-8", "gbk"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _read_output(self, name):
        # 逐行读取字节流，再自适应解码（兼容 UTF-8 / GBK 输出）
        try:
            for line in iter(self.process.stdout.readline, b""):
                if line:
                    text = self._decode_line(line)
                    self.append_log(text.rstrip("\r\n"))
            self.process.stdout.close()
        except Exception as e:
            self.append_log(f"[读取输出异常] {e}")
        finally:
            try:
                self.process.stdout.close()
            except Exception:
                pass

        ret = self.process.wait()
        self.process = None
        self.root.after(0, lambda: self._on_process_done(name, ret))

    def _on_process_done(self, name, ret):
        self.append_log("=" * 50)
        if ret == 0:
            self.append_log(f"==== [{name}] 运行结束（成功） ====")
            self.status_label.config(text=f"[{name}] 完成", foreground="#008000")
        else:
            self.append_log(f"==== [{name}] 运行结束（退出码 {ret}） ====")
            self.status_label.config(text=f"[{name}] 失败（退出码 {ret}）", foreground="#c00")

        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.append_log("\n输出文件在项目的 output 目录下。")

    def on_stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.append_log("[用户] 已发送停止信号...")
            self.stop_btn.config(state="disabled")

    def append_log(self, text):
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def on_open_output(self):
        name = self.project_var.get()
        out_dir = os.path.join(ROOT_DIR, PROJECTS[name]["dir"], "output")
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception:
                pass
        try:
            if os.name == "nt":
                os.startfile(out_dir)
            else:
                import subprocess
                subprocess.Popen(["open", out_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开输出目录：{e}")


def main():
    root = tk.Tk()
    # 尝试设置主题（可选）
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
