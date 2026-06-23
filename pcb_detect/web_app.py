# -*- coding: utf-8 -*-
"""
web_app.py —— PCB 缺陷检测网页上位机 Flask 后端
"""
import os
import sys
import time
import base64
import cv2
import numpy as np
import threading
import atexit
from flask import Flask, render_template, request, jsonify, Response, send_file, send_from_directory

# 将当前目录加入系统路径，确保正常导入 theme 和 detect
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import theme
from detect import PCBDetector

# 检测 Pillow/PIL 是否可用以实现中文重绘
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 初始化 Flask App
app = Flask(__name__,
            template_folder=os.path.join(HERE, "templates"),
            static_folder=os.path.join(HERE, "static"))

# 静态结果保存目录
RESULTS_DIR = os.path.join(HERE, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# 全局推理核心（单例）
detector = None
detector_error = None

try:
    detector = PCBDetector()
    print("模型与 NPU 初始化成功！")
except Exception as e:
    detector_error = str(e)
    print(f"警告：模型或 NPU 初始化失败！错误信息：{detector_error}")

# 注册程序退出时的资源释放
@atexit.register
def cleanup():
    global detector
    if detector:
        try:
            detector.release()
            print("NPU 资源已正常释放。")
        except Exception:
            pass

# ---------- 英文/标签重绘函数 ----------
def draw_chinese_labels(bgr_img, detections):
    """
    使用 Pillow 在图像上绘制英文标签和边框，实现清晰的英文标签重绘（避免中文乱码与字体缺失问题）。
    """
    if not HAS_PIL:
        return bgr_img
    
    # 转换 OpenCV (BGR) 为 PIL (RGB)
    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    draw = ImageDraw.Draw(pil_img)
    
    h, w = bgr_img.shape[:2]
    # 字体大小随图像大小动态缩放
    font_size = max(12, int(round(min(h, w) / 35)))
    
    # 寻找系统常见字体路径
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
        "C:\\Windows\\Fonts\\msyh.ttc"  # Windows 测试备用
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                pass
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            pass
            
    thickness = max(1, int(round(min(h, w) / 400)))
    
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        cls_en = d["cls_en"]
        conf = d["conf"]
        hex_color = theme.CLASS_COLORS_HEX.get(cls_en, "#00C8E0")
        
        # 十六进制颜色转 RGB 元组
        rgb_color = tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        
        # 绘制检测框
        try:
            draw.rectangle([x1, y1, x2, y2], outline=rgb_color, width=thickness)
        except TypeError:
            # 兼容低版本 Pillow
            draw.rectangle([x1, y1, x2, y2], outline=rgb_color)
            
        label = f"{cls_en} {conf:.2f}"
        
        # 计算标签文字背景框尺寸
        if font:
            try:
                if hasattr(font, 'getbbox'):
                    l_w, l_h = font.getbbox(label)[2:]
                else:
                    l_w, l_h = draw.textsize(label, font=font)
            except Exception:
                l_w, l_h = len(label) * (font_size * 0.7), font_size + 4
        else:
            l_w, l_h = len(label) * 8, 12
            
        ty = max(0, y1 - l_h - 4)
        draw.rectangle([x1, ty, x1 + l_w + 4, y1], fill=rgb_color)
        
        # 绘制英文文字，填充深色（接近 OpenCV 中的字体底色）
        draw.text((x1 + 2, ty + 2), label, fill=(10, 10, 10), font=font)
        
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


# ---------- 摄像头后台多线程控制 ----------
class CameraWorker:
    def __init__(self, pcb_detector):
        self.detector = pcb_detector
        self.cap = None
        self.thread = None
        self.active = False
        self.lock = threading.Lock()
        
        # 共享流状态
        self.latest_jpeg = None
        self.latest_detections = []
        self.latest_ms = 0.0
        self.latest_fps = 0.0
        
        # 参数
        self.chinese_redraw = True

    def start(self, device_id=0):
        with self.lock:
            if self.active:
                return True, "摄像头已在运行中"
            
            self.cap = cv2.VideoCapture(device_id)
            if not self.cap.isOpened():
                self.cap = None
                return False, f"无法打开摄像头设备 (ID: {device_id})"
                
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.active = True
            
            self.latest_jpeg = None
            self.latest_detections = []
            self.latest_ms = 0.0
            self.latest_fps = 0.0
            
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            return True, "摄像头启动成功"

    def stop(self):
        with self.lock:
            if not self.active:
                return True, "摄像头已处于停止状态"
            self.active = False
            
        if self.thread:
            self.thread.join(timeout=1.5)
            self.thread = None
            
        with self.lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.latest_jpeg = None
            self.latest_detections = []
            self.latest_ms = 0.0
            self.latest_fps = 0.0
        return True, "摄像头停止成功"

    def _run(self):
        prev_time = time.time()
        while True:
            with self.lock:
                if not self.active or self.cap is None:
                    break
                cap = self.cap
            
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            t_start = time.time()
            detections = []
            ms = 0.0
            
            # 目标检测
            if self.detector and self.detector.ready:
                try:
                    annotated, detections, ms = self.detector.detect(frame)
                    if self.chinese_redraw and HAS_PIL:
                        try:
                            annotated = draw_chinese_labels(frame, detections)
                        except Exception:
                            pass
                except Exception as e:
                    annotated = frame.copy()
                    cv2.putText(annotated, f"Error: {str(e)}", (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                annotated = frame.copy()
                cv2.putText(annotated, "Model/NPU Not Ready", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            # 计算帧率与耗时
            curr_time = time.time()
            dt = curr_time - prev_time
            fps = 1.0 / dt if dt > 0 else 0.0
            prev_time = curr_time
            
            # 编码为 JPEG 字节流
            ret_enc, jpeg = cv2.imencode('.jpg', annotated)
            
            with self.lock:
                if ret_enc:
                    self.latest_jpeg = jpeg.tobytes()
                self.latest_detections = detections
                self.latest_ms = ms
                self.latest_fps = fps
                
            time.sleep(0.01)

    def get_status(self):
        with self.lock:
            return {
                "active": self.active,
                "fps": round(self.latest_fps, 1),
                "ms": round(self.latest_ms, 1),
                "detections": self.latest_detections
            }

camera_worker = CameraWorker(detector)


# ---------- Flask 路由定义 ----------

@app.route('/')
def index():
    """主页路由"""
    return render_template("index.html")

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取当前推理模型和 NPU 状态"""
    global detector, detector_error
    return jsonify({
        "model_loaded": detector is not None and detector.ready,
        "npu_ready": detector is not None and detector.ready,
        "error": detector_error,
        "has_pil": HAS_PIL,
        "camera_active": camera_worker.active
    })

@app.route('/api/detect_image', methods=['POST'])
def detect_image():
    """单张图片上传检测"""
    global detector
    if 'image' not in request.files:
        return jsonify({"success": False, "error": "未上传图片文件"}), 400
        
    file = request.files['image']
    chinese_redraw = request.form.get("chinese_redraw", "true").lower() == "true"
    
    try:
        # 读取上传图像
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({"success": False, "error": "图片解码失败，请上传正确的图片"}), 400
            
        if detector is None or not detector.ready:
            return jsonify({"success": False, "error": f"推理模型未初始化，原因：{detector_error or '未知'}"}), 500
            
        # 推理检测
        annotated, detections, ms = detector.detect(img)
        
        # 中文重绘
        if chinese_redraw and HAS_PIL:
            try:
                annotated = draw_chinese_labels(img, detections)
            except Exception as e:
                print(f"中文重绘失败: {str(e)}")
                
        # 编码回 JPEG Base64
        ret, jpeg = cv2.imencode('.jpg', annotated)
        if not ret:
            return jsonify({"success": False, "error": "结果图像编码失败"}), 500
            
        base64_img = base64.b64encode(jpeg.tobytes()).decode('utf-8')
        
        return jsonify({
            "success": True,
            "image": "data:image/jpeg;base64," + base64_img,
            "detections": detections,
            "ms": round(ms, 1)
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"处理出错: {str(e)}"}), 500

@app.route('/api/start_camera', methods=['POST'])
def start_camera():
    """开启板端 USB 摄像头"""
    device_id = request.json.get("device_id", 0) if request.is_json else 0
    chinese_redraw = request.json.get("chinese_redraw", True) if request.is_json else True
    camera_worker.chinese_redraw = chinese_redraw
    
    success, msg = camera_worker.start(device_id)
    return jsonify({"success": success, "message": msg})

@app.route('/api/stop_camera', methods=['POST'])
def stop_camera():
    """停止板端 USB 摄像头"""
    success, msg = camera_worker.stop()
    return jsonify({"success": success, "message": msg})

@app.route('/api/camera_status', methods=['GET'])
def get_camera_status():
    """轮询摄像头最新检测明细和指标"""
    return jsonify(camera_worker.get_status())

@app.route('/video_feed')
def video_feed():
    """MJPEG 视频流传输路由"""
    if not camera_worker.active:
        # 如果未开启，则返回默认黑白提示图
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(dummy_frame, "Camera Inactive", (180, 240), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (138, 148, 163), 2)
        _, jpeg = cv2.imencode('.jpg', dummy_frame)
        return Response(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n',
                        mimetype='multipart/x-mixed-replace; boundary=frame')
                        
    def mjpeg_generator():
        while True:
            # 轮询最新的 JPEG 帧
            with camera_worker.lock:
                if not camera_worker.active:
                    break
                jpeg = camera_worker.latest_jpeg
                
            if jpeg is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.04)  # ~25 FPS 限制，降低网络开销
            
    return Response(mjpeg_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/batch_detect', methods=['POST'])
def batch_detect():
    """批量检测指定服务器文件夹路径"""
    global detector
    if not request.is_json:
        return jsonify({"success": False, "error": "无效的请求格式"}), 400
        
    directory = request.json.get("directory")
    chinese_redraw = request.json.get("chinese_redraw", True)
    
    if not directory:
        return jsonify({"success": False, "error": "请输入文件夹路径"}), 400
        
    dir_path = os.path.abspath(directory)
    if not os.path.isdir(dir_path):
        return jsonify({"success": False, "error": f"本地文件夹不存在：{directory}"}), 400
        
    valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.JPG', '.JPEG', '.PNG', '.BMP'}
    try:
        filenames = [f for f in os.listdir(dir_path) if os.path.splitext(f)[1] in valid_exts]
        filenames.sort()
    except Exception as e:
        return jsonify({"success": False, "error": f"无法读取目录：{str(e)}"}), 500
        
    if not filenames:
        return jsonify({"success": False, "error": "该目录下未找到支持的图片（.jpg, .png, .bmp等）"}), 400
        
    if detector is None or not detector.ready:
        return jsonify({"success": False, "error": f"推理模型未就绪：{detector_error or '未知'}"}), 500
        
    results = []
    total_ms = 0.0
    defect_counts = {cn: 0 for cn in theme.CLASS_NAMES_CN}
    total_defects = 0
    
    # 清空 results 目录以防止图片累积冲突
    for f in os.listdir(RESULTS_DIR):
        fpath = os.path.join(RESULTS_DIR, f)
        if os.path.isfile(fpath) and os.path.splitext(f)[1] in valid_exts:
            try:
                os.remove(fpath)
            except Exception:
                pass
                
    for fname in filenames:
        img_path = os.path.join(dir_path, fname)
        img = cv2.imread(img_path)
        if img is None:
            continue
            
        try:
            annotated, detections, ms = detector.detect(img)
            total_ms += ms
            total_defects += len(detections)
            for d in detections:
                defect_counts[d["cls_cn"]] += 1
                
            if chinese_redraw and HAS_PIL:
                try:
                    save_img = draw_chinese_labels(img, detections)
                except Exception:
                    save_img = annotated
            else:
                save_img = annotated
        except Exception as e:
            save_img = img
            detections = []
            ms = 0.0
            print(f"检测图片 {fname} 失败: {str(e)}")
            
        # 保存带框图到静态结果目录
        dest_path = os.path.join(RESULTS_DIR, fname)
        cv2.imwrite(dest_path, save_img)
        
        results.append({
            "filename": fname,
            "original_path": img_path,
            "result_url": f"/results/{fname}",
            "detections": detections,
            "ms": round(ms, 1)
        })
        
    avg_ms = total_ms / len(results) if results else 0.0
    summary = {
        "total_images": len(results),
        "total_defects": total_defects,
        "avg_ms": round(avg_ms, 1),
        "defect_counts": defect_counts
    }
    
    return jsonify({
        "success": True,
        "results": results,
        "summary": summary
    })

@app.route('/results/<filename>')
def serve_result(filename):
    """服务批量检测的带框输出图片"""
    return send_from_directory(RESULTS_DIR, filename)

@app.route('/api/get_original_image')
def get_original_image():
    """获取板端本地的原始输入图片（供批量网格大图查看）"""
    img_path = request.args.get('path')
    if not img_path or not os.path.exists(img_path):
        return "图片不存在", 404
    return send_file(img_path)


if __name__ == '__main__':
    # 监听 0.0.0.0, 端口 5000, RK3588 真实环境多路并存
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
