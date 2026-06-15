# 频率水印工具

这是一个 Windows 桌面工具，可以给图片写入 DCT 频域文字水印，并用同一密钥查看/提取水印。

## 直接运行

```powershell
python app.py
```

## 打包成 exe

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

生成文件：

```text
dist\FrequencyWatermarkTool.exe
```

也可以双击 `build_exe.bat` 进行打包。

## 使用方式

1. 在“添加水印”页选择图片。
2. 输入水印文字和密钥，调节水印强度。
3. 点击“生成并保存水印图”，推荐保存为 PNG。
4. 在“查看水印”页选择水印图，输入同一密钥，点击“查看水印”。

## 注意

- 查看水印需要使用写入时相同的密钥。
- 裁剪、缩放、低质量 JPEG 压缩可能破坏频域水印。
- 水印容量取决于图片尺寸，界面会显示可写入的最大字节数。
# pingyushuiying
