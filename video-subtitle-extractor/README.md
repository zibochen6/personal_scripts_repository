# 视频字幕批量提取工具

一个可直接运行的 Python CLI 工具，用于批量提取 YouTube 和 Bilibili 视频字幕，并按视频标题生成 Markdown 文件。

## 功能特性

- 支持 YouTube 与 Bilibili 混合链接批量处理
- 自动识别平台并提取视频标题
- 优先按语言偏好提取字幕，YouTube 支持 Transcript API 与 `yt-dlp` 双方案
- Bilibili 支持 `BV`、`av` 和 `b23.tv` 短链解析
- 每个视频输出一个 UTF-8 编码的 Markdown 文件
- 支持命令行输入、文件输入、交互式粘贴输入
- 支持时间戳保留、并发处理、Bilibili `SESSDATA` Cookie

## 安装

```bash
cd video-subtitle-extractor
pip install -r requirements.txt
```

## 如何启动

先进入项目目录：

```bash
cd video-subtitle-extractor
```

然后选择一种方式启动：

### 1. 直接传入一个或多个视频链接

```bash
python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "https://www.bilibili.com/video/BV1xx411c7mD"
```

### 2. 从文本文件批量启动

`urls.txt` 中每行放一个视频链接，然后运行：

```bash
python main.py -f urls.txt
python main.py -f urls.txt -o ./my_output
```

### 3. 交互式启动

运行下面命令后，把多个链接逐行粘贴进去，输入空行结束：

```bash
python main.py -i
```

### 4. 查看帮助

```bash
python main.py -h
```

## 常用启动示例

### 指定输出目录

```bash
python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -o ./output
```

### 保留时间戳

```bash
python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -t
```

### 指定语言优先级

```bash
python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -l zh-CN,en,ja
```

### 设置并发数量

```bash
python main.py -f urls.txt -c 5
```

### 处理需要登录的 Bilibili 视频

```bash
python main.py "https://www.bilibili.com/video/BVxxxx" --cookie "你的SESSDATA"
```

## 命令行参数

```text
位置参数:
  urls                 一个或多个视频 URL

可选参数:
  -f, --file           从文本文件中读取 URL，每行一个
  -i, --interactive    交互式粘贴 URL，输入空行结束
  -o, --output         输出目录，默认 ./output
  -t, --timestamps     在字幕中保留时间戳
  -l, --lang           字幕语言优先级，逗号分隔，如 zh-CN,en
  -c, --concurrent     并发数量，默认 5
  --cookie             Bilibili 的 SESSDATA Cookie 值
```

## 输出格式

每个视频会生成一个 `{视频标题}.md` 文件，内容格式如下：

```markdown
# 视频标题

> **平台**：YouTube
> **链接**：[原始链接](https://example.com)
> **字幕语言**：zh-CN
> **提取时间**：2026-03-12T21:00:00+08:00

---

字幕正文内容

---
```

## 常见错误

- `无法识别的视频链接`
  - URL 不符合支持的 YouTube / Bilibili 规则。
- `缺少第三方依赖`
  - 请先执行 `pip install -r requirements.txt`。
- `该视频没有可用的字幕内容`
  - 视频未提供 CC 字幕，或 YouTube/Bilibili 接口无法获取字幕。
- `该内容可能需要登录`
  - Bilibili 视频可能需要 `SESSDATA`。

## 测试建议

- YouTube 有手动字幕的视频
- YouTube 仅有自动字幕的视频
- YouTube 无字幕的视频
- Bilibili 有 CC 字幕的视频
- Bilibili 无字幕的视频
- 混合 URL 批量处理
- 无效 URL 报错
- 重复 URL 去重
- 特殊字符标题的文件名清洗
- `b23.tv` 短链解析

## 限制说明

- 网络访问依赖外部站点可用性。
- 部分字幕受地区、登录态、会员权限或接口变更影响。
- 当前实现默认提取 Bilibili 第一 P 的字幕。
