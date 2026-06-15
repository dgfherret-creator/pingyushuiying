from __future__ import annotations

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from watermark_core import WatermarkError, embed_watermark, extract_watermark, image_file_capacity


APP_TITLE = "频率水印工具"
IMAGE_TYPES = [
    ("图片文件", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.tif;*.tiff"),
    ("所有文件", "*.*"),
]

PHONE_W = 430
PHONE_H = 700


def _blend(start: str, end: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(start[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i : i + 2], 16) for i in (1, 3, 5))
    c = tuple(round(a[i] + (b[i] - a[i]) * amount) for i in range(3))
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def rounded_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    **kwargs,
) -> int:
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class WatermarkApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x760")
        self.minsize(760, 720)

        self.mode = tk.StringVar(value="embed")
        self.add_image_path = tk.StringVar()
        self.view_image_path = tk.StringVar()
        self.add_status = tk.StringVar(value="选择图片后写入频域水印")
        self.view_status = tk.StringVar(value="选择含水印图片后读取")
        self.capacity_text = tk.StringVar(value="容量：未选择图片")
        self.add_key = tk.StringVar()
        self.view_key = tk.StringVar()
        self.strength = tk.IntVar(value=28)
        self.add_progress = tk.DoubleVar(value=0)
        self.view_progress = tk.DoubleVar(value=0)
        self._preview_refs: list[ImageTk.PhotoImage] = []
        self._background_items: list[int] = []

        self._configure_style()
        self._build_ui()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "Glass.Horizontal.TProgressbar",
            troughcolor="#efe9ff",
            bordercolor="#efe9ff",
            background="#5d63f2",
            lightcolor="#5d63f2",
            darkcolor="#5d63f2",
        )

    def _build_ui(self) -> None:
        self.bg = tk.Canvas(self, highlightthickness=0)
        self.bg.pack(fill="both", expand=True)
        self.bg.bind("<Configure>", self._draw_background)

        self.phone_shadow = self.bg.create_rectangle(0, 0, 1, 1, outline="")
        self.phone_canvas = tk.Canvas(self.bg, width=PHONE_W, height=PHONE_H, highlightthickness=0)
        self.phone_window = self.bg.create_window(0, 0, window=self.phone_canvas, anchor="nw")

        self._draw_phone()
        self._build_phone_widgets()
        self._set_mode("embed")

    def _draw_background(self, event=None) -> None:
        width = max(self.bg.winfo_width(), 1)
        height = max(self.bg.winfo_height(), 1)
        for item in self._background_items:
            self.bg.delete(item)
        self._background_items.clear()

        for x in range(width):
            color = _blend("#2434c6", "#fff0e4", x / max(width - 1, 1))
            self._background_items.append(self.bg.create_line(x, 0, x, height, fill=color))

        self._background_items.append(
            self.bg.create_oval(-160, -110, 430, 470, fill="#6b5df4", outline="", stipple="gray25")
        )
        self._background_items.append(
            self.bg.create_oval(width - 410, 80, width + 140, height + 120, fill="#ff9f75", outline="", stipple="gray25")
        )
        self._background_items.append(
            self.bg.create_oval(width // 2 - 320, height - 320, width // 2 + 260, height + 190, fill="#f8e8ff", outline="", stipple="gray50")
        )

        x = (width - PHONE_W) // 2
        y = max(26, (height - PHONE_H) // 2)
        self.bg.coords(self.phone_window, x, y)
        self.bg.coords(self.phone_shadow, x + 20, y + 20, x + PHONE_W + 20, y + PHONE_H + 20)
        self.bg.itemconfigure(self.phone_shadow, fill="#17123d", stipple="gray75")
        self.bg.tag_lower(self.phone_shadow)
        for item in self._background_items:
            self.bg.tag_lower(item)
        self.bg.tag_raise(self.phone_shadow)
        self.bg.tag_raise(self.phone_window)

    def _draw_phone(self) -> None:
        canvas = self.phone_canvas
        canvas.delete("all")

        for y in range(PHONE_H):
            base = _blend("#fbf5ff", "#fff2e8", y / PHONE_H)
            canvas.create_line(0, y, PHONE_W, y, fill=base)

        rounded_rect(canvas, 8, 8, PHONE_W - 8, PHONE_H - 8, 34, fill="#ffffff", outline="#ffffff", stipple="gray50")
        rounded_rect(canvas, 16, 16, PHONE_W - 16, PHONE_H - 16, 30, fill="#fdf8ff", outline="#ffffff")
        rounded_rect(canvas, 24, 36, PHONE_W - 24, 182, 26, fill="#7667eb", outline="")
        rounded_rect(canvas, 24, 36, PHONE_W - 24, 182, 26, fill="#f1dbff", outline="", stipple="gray50")
        rounded_rect(canvas, 24, 196, PHONE_W - 24, 236, 20, fill="#ffffff", outline="", stipple="gray50")
        rounded_rect(canvas, 24, 250, PHONE_W - 24, 394, 24, fill="#ffffff", outline="", stipple="gray50")
        rounded_rect(canvas, 24, 408, PHONE_W - 24, 612, 24, fill="#ffffff", outline="", stipple="gray50")
        rounded_rect(canvas, 24, 624, PHONE_W - 24, 664, 20, fill="#5b63f1", outline="")

        canvas.create_text(48, 24, text="11:20", fill="#24223a", font=("Segoe UI", 8, "bold"), anchor="w")
        canvas.create_text(PHONE_W - 48, 24, text="5G  ▮▮", fill="#24223a", font=("Segoe UI", 8, "bold"), anchor="e")
        canvas.create_text(48, 60, text="MarkGlass", fill="#ffffff", font=("Segoe UI", 13, "bold"), anchor="w")
        canvas.create_text(48, 91, text="隐形频率水印", fill="#ffffff", font=("Microsoft YaHei UI", 24, "bold"), anchor="w")
        canvas.create_text(48, 122, text="DCT 频域写入 · 密钥保护 · 推荐 PNG", fill="#f5efff", font=("Microsoft YaHei UI", 10), anchor="w")
        rounded_rect(canvas, 48, 143, 166, 169, 13, fill="#ffffff", outline="")
        rounded_rect(canvas, PHONE_W - 166, 143, PHONE_W - 48, 169, 13, fill="#ffffff", outline="")
        canvas.create_text(107, 156, text="选择图片", fill="#25214b", font=("Microsoft YaHei UI", 9, "bold"))
        canvas.create_text(PHONE_W - 107, 156, text="执行操作", fill="#25214b", font=("Microsoft YaHei UI", 9, "bold"))

        canvas.create_text(48, 266, text="Image Preview", fill="#151528", font=("Segoe UI", 9, "bold"), anchor="w")
        canvas.create_text(48, 422, text="Watermark Panel", fill="#151528", font=("Segoe UI", 9, "bold"), anchor="w")
        canvas.create_text(PHONE_W // 2, 686, text="Home          Add          View          Profile", fill="#343044", font=("Segoe UI", 8))

    def _build_phone_widgets(self) -> None:
        self.embed_tab = tk.Button(
            self.phone_canvas,
            text="添加水印",
            command=lambda: self._set_mode("embed"),
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            activebackground="#ece8ff",
        )
        self.view_tab = tk.Button(
            self.phone_canvas,
            text="查看水印",
            command=lambda: self._set_mode("view"),
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            activebackground="#ece8ff",
        )
        self.phone_canvas.create_window(36, 202, width=176, height=28, window=self.embed_tab, anchor="nw")
        self.phone_canvas.create_window(218, 202, width=176, height=28, window=self.view_tab, anchor="nw")

        self.header_select_button = tk.Button(
            self.phone_canvas,
            text="选择图片",
            command=self._select_current_image,
            bg="#ffffff",
            fg="#25214b",
            activebackground="#f4f0ff",
            activeforeground="#25214b",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        self.header_action_button = tk.Button(
            self.phone_canvas,
            text="执行操作",
            command=self._primary_clicked,
            bg="#ffffff",
            fg="#25214b",
            activebackground="#f4f0ff",
            activeforeground="#25214b",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        self.phone_canvas.create_window(50, 145, width=114, height=22, window=self.header_select_button, anchor="nw")
        self.phone_canvas.create_window(PHONE_W - 164, 145, width=114, height=22, window=self.header_action_button, anchor="nw")

        self.preview = tk.Label(
            self.phone_canvas,
            text="点击下方按钮选择图片",
            bg="#fbf7ff",
            fg="#7f789a",
            font=("Microsoft YaHei UI", 10, "bold"),
            bd=0,
        )
        self.phone_canvas.create_window(48, 286, width=334, height=84, window=self.preview, anchor="nw")

        self.path_label = tk.Label(
            self.phone_canvas,
            text="尚未选择文件",
            bg="#fffafd",
            fg="#7c7495",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        )
        self.phone_canvas.create_window(48, 372, width=334, height=18, window=self.path_label, anchor="nw")

        self.form_frame = tk.Frame(self.phone_canvas, bg="#fffafd", bd=0)
        self.phone_canvas.create_window(42, 438, width=346, height=160, window=self.form_frame, anchor="nw")

        self.primary_button = tk.Button(
            self.phone_canvas,
            text="生成并保存水印图",
            command=self._primary_clicked,
            bg="#5b63f1",
            fg="#ffffff",
            activebackground="#4d54d8",
            activeforeground="#ffffff",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.phone_canvas.create_window(36, 631, width=358, height=26, window=self.primary_button, anchor="nw")

        self.progress = ttk.Progressbar(
            self.phone_canvas,
            maximum=100,
            variable=self.add_progress,
            mode="determinate",
            style="Glass.Horizontal.TProgressbar",
        )
        self.phone_canvas.create_window(48, 672, width=334, height=4, window=self.progress, anchor="nw")

        self.status_label = tk.Label(
            self.phone_canvas,
            textvariable=self.add_status,
            bg="#fff5ee",
            fg="#514b76",
            font=("Microsoft YaHei UI", 8),
        )
        self.phone_canvas.create_window(48, 608, width=334, height=14, window=self.status_label, anchor="nw")

    def _set_mode(self, mode: str) -> None:
        self.mode.set(mode)
        active = {"bg": "#5b63f1", "fg": "#ffffff", "activeforeground": "#ffffff"}
        inactive = {"bg": "#ffffff", "fg": "#5f5a7b", "activeforeground": "#5f5a7b"}
        if mode == "embed":
            self.embed_tab.configure(**active)
            self.view_tab.configure(**inactive)
            self.primary_button.configure(text="生成并保存水印图")
            self.header_action_button.configure(text="保存水印")
            self.progress.configure(variable=self.add_progress)
            self.status_label.configure(textvariable=self.add_status)
            self._build_embed_form()
            self._refresh_preview(self.add_image_path.get())
        else:
            self.embed_tab.configure(**inactive)
            self.view_tab.configure(**active)
            self.primary_button.configure(text="查看水印")
            self.header_action_button.configure(text="读取水印")
            self.progress.configure(variable=self.view_progress)
            self.status_label.configure(textvariable=self.view_status)
            self._build_view_form()
            self._refresh_preview(self.view_image_path.get())

    def _build_embed_form(self) -> None:
        self._clear_form()
        tk.Label(
            self.form_frame,
            textvariable=self.capacity_text,
            bg="#fffafd",
            fg="#736d8e",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x")

        self.message_text = tk.Text(
            self.form_frame,
            height=3,
            wrap="word",
            font=("Microsoft YaHei UI", 9),
            bg="#f6f1ff",
            fg="#1f1d31",
            relief="flat",
            insertbackground="#5b63f1",
            padx=10,
            pady=8,
            undo=True,
        )
        self.message_text.pack(fill="x", pady=(7, 7))

        row = tk.Frame(self.form_frame, bg="#fffafd")
        row.pack(fill="x")
        tk.Label(row, text="密钥", bg="#fffafd", fg="#151528", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.add_key_entry = tk.Entry(
            row,
            textvariable=self.add_key,
            bg="#f6f1ff",
            fg="#1f1d31",
            relief="flat",
            insertbackground="#5b63f1",
            font=("Microsoft YaHei UI", 9),
        )
        self.add_key_entry.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=4)

        strength_row = tk.Frame(self.form_frame, bg="#fffafd")
        strength_row.pack(fill="x", pady=(8, 0))
        tk.Label(strength_row, text="强度", bg="#fffafd", fg="#151528", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        tk.Label(strength_row, textvariable=self.strength, bg="#fffafd", fg="#5b63f1", font=("Segoe UI", 9, "bold")).pack(side="right")
        tk.Scale(
            self.form_frame,
            from_=8,
            to=80,
            variable=self.strength,
            orient="horizontal",
            showvalue=False,
            bg="#fffafd",
            troughcolor="#ebe8fb",
            activebackground="#5b63f1",
            highlightthickness=0,
            bd=0,
            command=lambda value: self.strength.set(round(float(value))),
        ).pack(fill="x")

    def _build_view_form(self) -> None:
        self._clear_form()
        row = tk.Frame(self.form_frame, bg="#fffafd")
        row.pack(fill="x")
        tk.Label(row, text="密钥", bg="#fffafd", fg="#151528", font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.view_key_entry = tk.Entry(
            row,
            textvariable=self.view_key,
            bg="#f6f1ff",
            fg="#1f1d31",
            relief="flat",
            insertbackground="#5b63f1",
            font=("Microsoft YaHei UI", 9),
        )
        self.view_key_entry.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=4)

        tk.Label(
            self.form_frame,
            text="提取结果",
            bg="#fffafd",
            fg="#151528",
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(10, 4))

        self.result_text = tk.Text(
            self.form_frame,
            height=5,
            wrap="word",
            font=("Microsoft YaHei UI", 9),
            bg="#f6f1ff",
            fg="#1f1d31",
            relief="flat",
            padx=10,
            pady=8,
            state="disabled",
        )
        self.result_text.pack(fill="both", expand=True)

    def _clear_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()

    def _primary_clicked(self) -> None:
        if self.mode.get() == "embed":
            self._embed_clicked()
        else:
            self._extract_clicked()

    def _select_current_image(self) -> None:
        if self.mode.get() == "embed":
            self._select_add_image()
        else:
            self._select_view_image()

    def _refresh_preview(self, path: str) -> None:
        if not path:
            self.preview.configure(image="", text="点击顶部按钮选择图片")
            self.path_label.configure(text="尚未选择文件")
            return
        self._show_preview(path)
        self.path_label.configure(text=Path(path).name)

    def _select_add_image(self) -> None:
        path = filedialog.askopenfilename(title="选择要添加水印的图片", filetypes=IMAGE_TYPES)
        if not path:
            return
        self.add_image_path.set(path)
        self._refresh_preview(path)
        self._update_capacity(path)
        self.add_status.set("已选择图片，可以写入水印")

    def _select_view_image(self) -> None:
        path = filedialog.askopenfilename(title="选择要查看水印的图片", filetypes=IMAGE_TYPES)
        if not path:
            return
        self.view_image_path.set(path)
        self._refresh_preview(path)
        self.view_status.set("已选择图片，可以读取水印")
        self._set_result("")

    def _embed_clicked(self) -> None:
        input_path = self.add_image_path.get()
        message = self.message_text.get("1.0", "end").strip()
        if not input_path:
            self._select_add_image()
            return
        if not message:
            messagebox.showwarning(APP_TITLE, "请输入水印文字。")
            return

        source = Path(input_path)
        default_name = f"{source.stem}_watermarked.png"
        output_path = filedialog.asksaveasfilename(
            title="保存水印图",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[
                ("PNG 图片", "*.png"),
                ("JPEG 图片", "*.jpg;*.jpeg"),
                ("BMP 图片", "*.bmp"),
                ("WEBP 图片", "*.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not output_path:
            return

        self.add_progress.set(0)
        self.add_status.set("正在写入频域水印...")
        self.primary_button.configure(state="disabled")

        def worker() -> None:
            try:
                result = embed_watermark(
                    input_path,
                    output_path,
                    message,
                    key=self.add_key.get(),
                    strength=self.strength.get(),
                    progress_callback=lambda done, total: self.after(0, self._update_add_progress, done, total),
                )
            except Exception as exc:
                self.after(0, self._embed_failed, exc)
            else:
                self.after(0, self._embed_finished, result)

        threading.Thread(target=worker, daemon=True).start()

    def _extract_clicked(self) -> None:
        input_path = self.view_image_path.get()
        if not input_path:
            self._select_view_image()
            return

        self.view_progress.set(0)
        self.view_status.set("正在读取频域水印...")
        self.primary_button.configure(state="disabled")
        self._set_result("")

        def worker() -> None:
            try:
                result = extract_watermark(
                    input_path,
                    key=self.view_key.get(),
                    progress_callback=lambda done, total: self.after(0, self._update_view_progress, done, total),
                )
            except Exception as exc:
                self.after(0, self._extract_failed, exc)
            else:
                self.after(0, self._extract_finished, result)

        threading.Thread(target=worker, daemon=True).start()

    def _embed_finished(self, result) -> None:
        self.primary_button.configure(state="normal")
        self.add_progress.set(100)
        self.add_status.set(f"已保存：{result.output_path.name}，写入 {result.text_bytes} 字节")
        self.add_image_path.set(str(result.output_path))
        self._refresh_preview(str(result.output_path))
        messagebox.showinfo(APP_TITLE, f"水印图已保存：\n{result.output_path}")

    def _embed_failed(self, exc: Exception) -> None:
        self.primary_button.configure(state="normal")
        self.add_progress.set(0)
        text = str(exc) if isinstance(exc, WatermarkError) else f"处理失败：{exc}"
        self.add_status.set(text)
        messagebox.showerror(APP_TITLE, text)

    def _extract_finished(self, result) -> None:
        self.primary_button.configure(state="normal")
        self.view_progress.set(100)
        self.view_status.set(f"已读取 {result.text_bytes} 字节水印")
        self._set_result(result.message)

    def _extract_failed(self, exc: Exception) -> None:
        self.primary_button.configure(state="normal")
        self.view_progress.set(0)
        text = str(exc) if isinstance(exc, WatermarkError) else f"读取失败：{exc}"
        self.view_status.set(text)
        self._set_result("")
        messagebox.showerror(APP_TITLE, text)

    def _update_add_progress(self, done: int, total: int) -> None:
        self.add_progress.set((done / max(total, 1)) * 100)

    def _update_view_progress(self, done: int, total: int) -> None:
        self.view_progress.set((done / max(total, 1)) * 100)

    def _update_capacity(self, path: str) -> None:
        try:
            capacity = image_file_capacity(path)
            self.capacity_text.set(f"{capacity.width}x{capacity.height} · 最多约 {capacity.max_text_bytes} 字节")
        except Exception as exc:
            self.capacity_text.set(f"容量读取失败：{exc}")

    def _set_result(self, text: str) -> None:
        if not hasattr(self, "result_text") or not self.result_text.winfo_exists():
            return
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        if text:
            self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _show_preview(self, path: str | Path) -> None:
        try:
            with Image.open(path) as image:
                image.thumbnail((334, 84), Image.Resampling.LANCZOS)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA")
                photo = ImageTk.PhotoImage(image)
            self._preview_refs.append(photo)
            if len(self._preview_refs) > 4:
                self._preview_refs = self._preview_refs[-4:]
            self.preview.configure(image=photo, text="")
        except Exception as exc:
            self.preview.configure(image="", text=f"预览失败：{exc}")


if __name__ == "__main__":
    app = WatermarkApp()
    app.mainloop()
