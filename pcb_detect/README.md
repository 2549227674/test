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
