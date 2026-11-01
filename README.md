# 韶律 · 音乐格式转换器

基于 PySide6 和 FFmpeg 的本地批量音乐转换器，重点支持网易云音乐 `.ncm` 文件、320 kbps MP3 输出、歌手-歌曲名重命名、分类目录及 LRC 歌词匹配。

[![Tests](https://github.com/wwlswj/music-format-converter/actions/workflows/tests.yml/badge.svg)](https://github.com/wwlswj/music-format-converter/actions/workflows/tests.yml)

![韶律界面预览](docs/preview.png)

## 环境要求

- Windows 10/11 x64
- Python 3.12 或更高版本，推荐 Python 3.14
- 首次安装时需要联网下载 Python 依赖和 FFmpeg

## 功能

- 输入：NCM、MP3、FLAC、WAV、APE、M4A、AAC、OGG、Opus、WMA、AIFF、ALAC。
- 输出：MP3、FLAC、WAV、M4A、ALAC、OGG、Opus、WMA、AIFF、APE。
- 有损格式默认 320 kbps；无损格式自动忽略比特率。
- 默认重命名为 `歌手 - 歌曲名`，同名文件自动编号。
- 默认不建立分类子目录；可独立选择按歌手、风格、专辑分类。
- 歌词按“NCM/音频内嵌 → 本地 LRC → LRCLIB”顺序解析。
- NCM 音频分块解密，解密后必须通过 FFprobe 验证。
- 提供无界面 CLI 及 Codex、Claude Code、DeepSeek Harness 共用 Skill。

## 启动

克隆仓库后，首次安装或修复：

```powershell
git clone https://github.com/wwlswj/music-format-converter.git
cd music-format-converter
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

`setup.ps1` 会创建 `.venv`、安装 Python 依赖、下载固定版本 FFmpeg、校验 SHA-256，并生成本机启动快捷方式。

启动界面：

```powershell
.\run.ps1
```

推荐双击无控制台的 `启动韶律.lnk`。

`启动韶律.bat` 会保留“韶律启动器”控制台窗口；正常关闭软件后控制台自动退出，启动失败时会暂停并显示日志位置。也可以直接运行：

```powershell
.\.venv\Scripts\python.exe app.py
```

如果启动失败，程序会显示原生错误对话框，详细堆栈优先写入
`.music-converter-data\logs\launcher.log`。

如果移动了项目目录，请重新运行：

```powershell
.\scripts\create_shortcuts.ps1
```

## 命令行

```powershell
.\.venv\Scripts\music-converter.exe doctor --json

.\.venv\Scripts\music-converter.exe convert "D:\Music" `
  --output "D:\Converted" `
  --format mp3 `
  --bitrate 320 `
  --group-by artist `
  --json
```

默认参数：

- 格式 `mp3`
- 比特率 `320`
- 命名模板 `{artist} - {title}`
- 不分类
- 开启歌词匹配
- 同名文件自动添加 `(2)`、`(3)`

## Skill

权威 Skill 位于：

```text
.agents/skills/music-format-converter/
```

同步 Claude Code 项目级 Skill：

```powershell
.\.venv\Scripts\python.exe scripts\sync_skills.py
```

同时安装到用户级目录：

```powershell
.\.venv\Scripts\python.exe scripts\sync_skills.py --user
```

目标目录：

- Codex、DeepSeek Harness：`~/.agents/skills/music-format-converter/`
- Claude Code：`~/.claude/skills/music-format-converter/`

## 歌词与隐私

音频和 NCM 解密全部在本机执行。需要自动歌词时，仅将歌曲名、歌手、专辑和时长发送至 LRCLIB，不上传音频。关闭“自动匹配歌词”即可完全禁用联网歌词查询。

歌词匹配无法保证覆盖所有歌曲。低置信度候选会进入“歌词待确认”，程序不会编造歌词或时间轴。纯音乐不会生成空 LRC。

## 使用边界

NCM 支持仅用于处理用户合法取得并保存在本机的文件。本软件不提供音乐下载、付费内容绕过或内容分享功能。

APE 输出依赖官方 Monkey's Audio `MAC.exe`。其他第三方组件和许可证说明见 `THIRD_PARTY_NOTICES.md`。

## 测试

```powershell
.\scripts\test.ps1
```

测试使用自行生成的音频、图片和 NCM 合成样本，不包含受版权保护的音乐。

## 许可

项目源代码采用 [MIT License](LICENSE)。PySide6、FFmpeg、Monkey's Audio、字体、Mutagen 等第三方组件继续适用其各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。


