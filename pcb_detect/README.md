# PCB 缺陷检测上位机（RK3588 · PyQt5 · 深色工业风）

基于瑞芯微 RK3588 NPU 的 PCB 缺陷检测桌面程序。使用已转换好的 YOLOv5
RKNN 模型，对 PCB 图像 / USB 摄像头画面做 6 类缺陷的实时检测，并以深色
工业风界面展示检测框、明细表与统计图表。

> 适用场景：高校课程实训 / 现场演示。界面专业、可交互、可现场操作。

## 一、功能

- **单张图片检测**：选图 → 显示带框结果 → 刷新明细表 → 计入统计。
- **摄像头实时检测**：开摄像头逐帧检测，FPS 实时更新，可随时停止。
- **批量检测文件夹**：逐张检测，带框结果存 `results/`，进度条体现进度，
  全部计入统计（一次刷出好看的统计图）。
- **统计面板**：每类缺陷数量柱状图 + 累计图片/帧数、缺陷总数、平均推理
  耗时(ms)、平均 FPS。
- **状态栏**：模型 / NPU 状态彩色圆点、实时 FPS 与最近耗时。

## 二、6 类缺陷

| 英文 | 中文 |
|------|------|
| missing_hole | 漏孔 |
| mouse_bite | 鼠咬 |
| open_circuit | 开路 |
| short | 短路 |
| spur | 毛刺 |
| spurious_copper | 杂铜 |

## 三、运行环境

- 硬件：RK3588 实验箱（自带显示屏 + Linux 桌面 + USB 摄像头）。
- 板端已装：Python3、`rknn-toolkit-lite2`（`rknnlite`）、opencv-python、
  numpy、NPU 驱动。
- 模型：`model/yolov5s_pcb.rknn`（约 4.9MB，PCB 6 类缺陷）。

## 四、安装依赖

```bash
# PyQt5 推荐用系统包
sudo apt install python3-pyqt5

# 其余 Python 依赖
pip3 install -r requirements.txt
```

> `rknn-toolkit-lite2` 板端系统自带，**不在** `requirements.txt` 中。

如果界面中文显示成方块，安装中文字体：

```bash
sudo apt install fonts-noto-cjk
```

## 五、运行步骤

1. 把模型放到 `model/yolov5s_pcb.rknn`，测试图放到 `test_images/`。
2. **先跑探针**确认模型输出形状：

   ```bash
   python3 probe.py
   ```

   - 若打印 `outputs[0].shape = (1, 25200, 11)` → 解码用默认单张量路径，
     无需改动。
   - 若是 3 个特征图（如 `(1,255,80,80)` 等）→ `detect.py` 已内置 3 特征图
     解码分支，会自动识别；把打印结果贴回来确认即可。

3. 启动上位机：

   ```bash
   python3 main.py
   ```

## 六、坐标 / 归一化说明（如检测框偏移看这里）

- 预处理：letterbox 等比缩放 + 补黑边，BGR→RGB。
- 阈值：`CONF_THRESHOLD=0.25`，NMS `IOU_THRESHOLD=0.45`。
- 坐标还原：解码后的框统一换算到 640 像素空间，再
  `(coord - pad) / scale` 还原到原图。
- `detect.py` 顶部开关 `OUTPUT_XYWH_NORMALIZED`：
  - 默认 `True`（按需求文档，单张量输出 xywh 视为 0~1 归一化，乘 640）。
  - 若 probe 显示输出 xywh 已是 640 像素值，则改成 `False`。
- RKNN 量化模型通常转换时已配 mean/std，脚本里**不再** `/255`；probe 阶段确认。
- OpenCV 的 `putText` 不支持中文，检测框上的标签用英文类名 + 置信度，
  中文类名在右侧明细表展示。

## 七、文件结构

```
pcb_detect/
├── model/yolov5s_pcb.rknn   # 模型（自行放入）
├── test_images/             # 测试图（自行放入）
├── theme.py                 # 配色常量 + 全局 QSS
├── probe.py                 # 输出形状探针（最先跑）
├── detect.py                # 推理核心 PCBDetector
├── camera_thread.py         # 摄像头 / 批量 QThread
├── main_window.py           # 主窗口与界面逻辑
├── main.py                  # 入口
├── results/                 # 批量输出（运行时生成）
├── requirements.txt
└── README.md
```

## 八、说明

- Claude Code 在沙箱中无法访问 RK3588 / NPU / 摄像头，源码已做语法与静态
  检查；真机运行由使用者完成。涉及硬件处对导入失败、模型缺失、摄像头打不开
  均有清晰中文报错，不会直接崩溃。
- 配色 / 字体 / 样式集中在 `theme.py`，全局统一；推理核心 `detect.py` 与界面解耦。

## 九、网页版上位机（Flask 完整版）

为了支持在**纯 SSH / 无桌面环境的 RK3588 板端**上运行展示，项目新增了与 PyQt 版本功能完全对等的 **Flask 网页上位机版**。

### 1. 新增文件结构
```
pcb_detect/
├── web_app.py             # Flask 后端（路由 + MJPEG 视频流 + 批量处理）
├── templates/
│   └── index.html         # 单页面 Dashboard 模板
└── static/
    ├── style.css          # 深色工业风样式表（与 PyQt 一致）
    └── app.js             # 前端控制逻辑（Chart.js、实时轮询与双图比对）
```

### 2. 功能特点
- **单图检测**：上传单张图片，即可完成检测，并在大图框内展示带有缺陷标框的结果图与右侧明细列表。
- **实时检测 (USB 摄像头)**：支持板端 USB 摄像头数据读取与 NPU 检测，通过高效的 **MJPEG 流**推流至前端，前端以 **250ms/次** 轮询状态更新最新的缺陷列表、平均 FPS、NPU 耗时等指标。
- **批量文件夹检测**：指定板端本地的一个文件夹，后台依次读取、推理、将带框结果保存至 `results/` 并返回列表。前端以**网格缩略图卡片**形式渲染每张结果，支持**点击任意卡片弹出双图大图比对窗口（原图 vs 带框图）**。
- **Chart.js 缺陷图表**：实时/批量/单图检测的各类缺陷数量将累加更新至图表中，各缺陷色值与 `theme.py` 规定的一一对应。
- **中文画框重绘**：由于 OpenCV 不支持中文，后端集成了 Pillow 重绘逻辑。开启后可在前端检测图上直观看到中文标签（如 `漏孔 0.89`）。若中文显示为乱码或方块，请确保安装了系统字体：`sudo apt install fonts-noto-cjk`。

### 3. 网页版启动与访问步骤
1. **安装依赖**：
   确保安装了 Flask 和 Pillow：
   ```bash
   pip3 install -r requirements.txt
   ```
2. **运行服务**：
   在板端运行：
   ```bash
   python3 web_app.py
   ```
   终端会输出提示 `* Running on all addresses (0.0.0.0)`，监听端口为 `5000`。
3. **访问界面**：
   在同一局域网的笔记本浏览器中输入：
   ```
   http://<RK3588_IP>:5000
   ```
   即可访问完整版的深色工业风上位机页面，进行上传图片、控制摄像头或进行批量检测。
