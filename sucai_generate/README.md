# Pexels 视频下载脚本

这是一个基于 Python 的脚本，用于根据关键词从 [Pexels](https://www.pexels.com/zh-cn/) 批量下载高质量视频素材。

**注意：API Key 已经配置在脚本中，直接运行即可。**

## 环境准备

1.  **安装 Python 3.x**: 确保电脑上安装了 Python。
2.  **安装依赖库**:
    在终端（Terminal 或 CMD）中运行以下命令安装所需的第三方库：

    ```bash
    pip install -r requirements.txt
    ```

## 使用方法

### 方式 1：交互式运行
直接运行脚本，根据提示输入关键词和下载数量：

```bash
python pexels_downloader.py
```
*   脚本会提示输入关键词（例如：`nature`，`城市`，`technology`）。
*   脚本会提示输入下载数量（例如：`10`）。

### 方式 2：命令行参数运行
可以在运行命令时直接指定关键词和数量，实现快速下载：

```bash
# 语法: python pexels_downloader.py [关键词] [数量]

# 示例：下载 5 个关于 "sky" 的视频
python pexels_downloader.py "sky" 5

# 示例：下载 20 个关于 "猫" 的视频
python pexels_downloader.py "cat" 20
```

## 输出结果

*   脚本会在当前目录下创建一个名为 `{关键词}_videos` 的文件夹（例如 `sky_videos`）。
*   所有下载的高清视频都会保存在该文件夹中。
*   脚本会自动选择最高画质（通常为 HD 或 4K）的 MP4 文件进行下载。

## 常见问题

*   **下载速度慢？** 下载速度取决于网络环境和 Pexels 服务器。脚本已经启用了多线程下载来加速。
*   **找不到视频？** 尝试更换关键词（建议使用英文关键词，搜索结果通常更准确）。
