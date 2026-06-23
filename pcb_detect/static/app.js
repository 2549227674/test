// ---------- 全局状态定义 ----------
const STATE = {
    // 累计统计指标
    totalFrames: 0,
    totalDefects: 0,
    accumulatedMs: 0.0,
    accumulatedFps: 0.0,
    fpsCount: 0,
    
    // 每类缺陷累计计数 (与 theme.py 严格一致)
    defectCounts: {
        "missing_hole": 0,    // 漏孔
        "mouse_bite": 0,      // 鼠咬
        "open_circuit": 0,    // 开路
        "short": 0,           // 短路
        "spur": 0,            // 毛刺
        "spurious_copper": 0  // 杂铜
    },
    
    // 批量检测结果缓存 (用于网格大图比对)
    batchResults: {},
    
    // 实时相机状态轮询 Interval
    cameraPollInterval: null
};

// 缺陷中英文映射
const CN_TO_EN = {
    "漏孔": "missing_hole",
    "鼠咬": "mouse_bite",
    "开路": "open_circuit",
    "短路": "short",
    "毛刺": "spur",
    "杂铜": "spurious_copper"
};

const EN_TO_CN = {
    "missing_hole": "漏孔",
    "mouse_bite": "鼠咬",
    "open_circuit": "开路",
    "short": "短路",
    "spur": "毛刺",
    "spurious_copper": "杂铜"
};

// 类别固定颜色 (用于 Chart.js 柱状图)
const COLOR_MAPPING = {
    "missing_hole": "#FF5C5C",
    "mouse_bite": "#FFB020",
    "open_circuit": "#00C8E0",
    "short": "#A66BFF",
    "spur": "#28C76F",
    "spurious_copper": "#FF7AC6"
};

const LABELS_CN = ["漏孔", "鼠咬", "开路", "短路", "毛刺", "杂铜"];
const KEYS_EN = ["missing_hole", "mouse_bite", "open_circuit", "short", "spur", "spurious_copper"];
const CHART_COLORS = KEYS_EN.map(key => COLOR_MAPPING[key]);

// ---------- Chart.js 统计图表初始化 ----------
let defectChart = null;

function initChart() {
    const ctx = document.getElementById('defect-chart').getContext('2d');
    
    defectChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: LABELS_CN,
            datasets: [{
                data: KEYS_EN.map(key => STATE.defectCounts[key]),
                backgroundColor: CHART_COLORS,
                borderColor: 'transparent',
                borderWidth: 0,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `缺陷数量: ${context.parsed.y}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(42, 49, 59, 0.3)'
                    },
                    ticks: {
                        color: '#8A94A3',
                        font: {
                            family: 'Noto Sans CJK SC, Microsoft YaHei, sans-serif',
                            size: 11
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(42, 49, 59, 0.3)'
                    },
                    ticks: {
                        color: '#8A94A3',
                        stepSize: 1,
                        font: {
                            family: 'DejaVu Sans Mono, monospace',
                            size: 11
                        }
                    }
                }
            }
        }
    });
}

function updateChart() {
    if (defectChart) {
        defectChart.data.datasets[0].data = KEYS_EN.map(key => STATE.defectCounts[key]);
        defectChart.update();
    }
}

// ---------- UI 提示辅助 ----------
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast';
    if (type === 'danger') toast.classList.add('danger');
    if (type === 'success') toast.classList.add('success');
    
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

// ---------- API: 获取 NPU 与模型加载状态 ----------
async function checkSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        const modelStatusEl = document.getElementById('model-status');
        const npuStatusEl = document.getElementById('npu-status');
        
        if (data.model_loaded) {
            modelStatusEl.innerHTML = '<span class="dot ok"></span>模型 已加载';
        } else {
            modelStatusEl.innerHTML = '<span class="dot danger"></span>模型 加载失败';
            showToast(`模型加载异常: ${data.error || "未知原因"}`, 'danger');
        }
        
        if (data.npu_ready) {
            npuStatusEl.innerHTML = '<span class="dot ok"></span>NPU 就绪';
        } else {
            npuStatusEl.innerHTML = '<span class="dot danger"></span>NPU 离线';
        }
    } catch (err) {
        showToast('获取板端系统状态失败，请检查 Flask 是否运行中。', 'danger');
    }
}

// ---------- 更新累计统计指标显示 ----------
function updateStatsUI() {
    document.getElementById('stat-total-frames').textContent = STATE.totalFrames;
    document.getElementById('stat-total-defects').textContent = STATE.totalDefects;
    
    const avgMs = STATE.totalFrames > 0 ? (STATE.accumulatedMs / STATE.totalFrames).toFixed(1) : "0.0";
    document.getElementById('stat-avg-ms').textContent = avgMs;
    
    const avgFps = STATE.fpsCount > 0 ? (STATE.accumulatedFps / STATE.fpsCount).toFixed(1) : "0.0";
    document.getElementById('stat-avg-fps').textContent = avgFps;
}

// ---------- 清空统计数据 ----------
function resetStats() {
    STATE.totalFrames = 0;
    STATE.totalDefects = 0;
    STATE.accumulatedMs = 0.0;
    STATE.accumulatedFps = 0.0;
    STATE.fpsCount = 0;
    
    KEYS_EN.forEach(key => STATE.defectCounts[key] = 0);
    
    updateStatsUI();
    updateChart();
    
    // 清空当前页面检测表格
    const tbody = document.getElementById('detail-table-body');
    tbody.innerHTML = '<tr><td colspan="4" class="no-data">无检测数据</td></tr>';
    
    document.getElementById('top-fps').textContent = '0.0';
    document.getElementById('top-ms').textContent = '0.0';
    
    showToast('统计数据已清空。', 'success');
}

// ---------- 填充检测明细表 ----------
function populateDetailTable(detections, tbodyId = 'detail-table-body') {
    const tbody = document.getElementById(tbodyId);
    tbody.innerHTML = '';
    
    if (!detections || detections.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="no-data">无缺陷目标</td></tr>`;
        return;
    }
    
    detections.forEach((d, idx) => {
        const tr = document.createElement('tr');
        
        // 缺陷类别小角标样式
        const key = d.cls_en;
        const color = COLOR_MAPPING[key] || 'var(--accent-color)';
        
        // 坐标格式化
        const boxStr = `[${d.box.join(', ')}]`;
        
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td><span class="defect-label" style="background-color: ${color};">${d.cls_en}</span></td>
            <td class="font-mono">${(d.conf * 100).toFixed(0)}%</td>
            <td class="coord-text font-mono">${boxStr}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ---------- 1. 单张图片上传检测 ----------
async function uploadAndDetectImage() {
    const fileInput = document.getElementById('image-input');
    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('请先选择图片文件。', 'warning');
        return;
    }
    
    const chineseRedraw = document.getElementById('chinese-redraw-checkbox').checked;
    const formData = new FormData();
    formData.append('image', fileInput.files[0]);
    formData.append('chinese_redraw', chineseRedraw);
    
    const detectBtn = document.getElementById('detect-image-btn');
    detectBtn.disabled = true;
    detectBtn.textContent = '检测中...';
    
    try {
        const response = await fetch('/api/detect_image', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (data.success) {
            // 更新图像展示
            const mainImg = document.getElementById('main-display-img');
            const placeholder = document.getElementById('display-placeholder');
            mainImg.src = data.image;
            mainImg.style.display = 'block';
            placeholder.style.display = 'none';
            
            // 切换到单图视图
            switchTab('single');
            
            // 更新顶栏指标
            document.getElementById('top-ms').textContent = data.ms.toFixed(1);
            document.getElementById('top-fps').textContent = 'N/A';
            
            // 更新累计统计数据
            STATE.totalFrames += 1;
            STATE.accumulatedMs += data.ms;
            STATE.totalDefects += data.detections.length;
            
            data.detections.forEach(d => {
                const key = d.cls_en;
                if (key in STATE.defectCounts) {
                    STATE.defectCounts[key] += 1;
                }
            });
            
            updateStatsUI();
            updateChart();
            
            // 更新检测明细表格
            populateDetailTable(data.detections);
            
            showToast('单张检测完成。', 'success');
        } else {
            showToast(`检测失败: ${data.error}`, 'danger');
        }
    } catch (err) {
        showToast(`请求失败: ${err.message}`, 'danger');
    } finally {
        detectBtn.disabled = false;
        detectBtn.textContent = '执行检测';
    }
}

// ---------- 2. 板端 USB 实时检测 ----------
async function startCamera() {
    const deviceId = parseInt(document.getElementById('camera-device-id').value) || 0;
    const chineseRedraw = document.getElementById('chinese-redraw-checkbox').checked;
    
    try {
        const response = await fetch('/api/start_camera', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, chinese_redraw: chineseRedraw })
        });
        const data = await response.json();
        
        if (data.success) {
            // 界面切换
            const mainImg = document.getElementById('main-display-img');
            const placeholder = document.getElementById('display-placeholder');
            
            // 直接渲染 MJPEG 视频流地址
            mainImg.src = '/video_feed?' + Date.now();
            mainImg.style.display = 'block';
            placeholder.style.display = 'none';
            
            switchTab('single');
            
            // 按钮状态切换
            document.getElementById('start-camera-btn').disabled = true;
            document.getElementById('stop-camera-btn').disabled = false;
            
            // 启动定时轮询摄像头参数
            startCameraPolling();
            showToast('实时检测相机已开启', 'success');
        } else {
            showToast(`启动摄像头失败: ${data.message}`, 'danger');
        }
    } catch (err) {
        showToast(`启动摄像头请求异常: ${err.message}`, 'danger');
    }
}

async function stopCamera() {
    try {
        const response = await fetch('/api/stop_camera', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            // 停止轮询
            stopCameraPolling();
            
            // 按钮状态切换
            document.getElementById('start-camera-btn').disabled = false;
            document.getElementById('stop-camera-btn').disabled = true;
            
            // 重设图片框
            const mainImg = document.getElementById('main-display-img');
            mainImg.src = '';
            mainImg.style.display = 'none';
            
            const placeholder = document.getElementById('display-placeholder');
            placeholder.style.display = 'flex';
            
            showToast('实时检测相机已关闭', 'success');
        }
    } catch (err) {
        showToast('关闭相机时发生连接错误', 'danger');
    }
}

function startCameraPolling() {
    if (STATE.cameraPollInterval) clearInterval(STATE.cameraPollInterval);
    
    STATE.cameraPollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/camera_status');
            const data = await response.json();
            
            if (data.active) {
                // 更新顶栏
                document.getElementById('top-fps').textContent = data.fps.toFixed(1);
                document.getElementById('top-ms').textContent = data.ms.toFixed(1);
                
                // 累计累加
                STATE.totalFrames += 1;
                STATE.accumulatedMs += data.ms;
                STATE.accumulatedFps += data.fps;
                STATE.fpsCount += 1;
                STATE.totalDefects += data.detections.length;
                
                data.detections.forEach(d => {
                    const key = d.cls_en;
                    if (key in STATE.defectCounts) {
                        STATE.defectCounts[key] += 1;
                    }
                });
                
                // 更新 UI
                updateStatsUI();
                updateChart();
                populateDetailTable(data.detections);
            } else {
                stopCameraPolling();
            }
        } catch (err) {
            console.error('实时状态同步失败', err);
        }
    }, 250); // 每 250ms 轮询一次
}

function stopCameraPolling() {
    if (STATE.cameraPollInterval) {
        clearInterval(STATE.cameraPollInterval);
        STATE.cameraPollInterval = null;
    }
}

// ---------- 3. 批量检测文件夹 ----------
async function runBatchDetect() {
    const dirPath = document.getElementById('batch-dir-path').value.trim();
    if (!dirPath) {
        showToast('请输入板端有效的图片文件夹路径。', 'warning');
        return;
    }
    
    const chineseRedraw = document.getElementById('chinese-redraw-checkbox').checked;
    const batchBtn = document.getElementById('start-batch-btn');
    batchBtn.disabled = true;
    batchBtn.textContent = '批量处理中...';
    
    try {
        const response = await fetch('/api/batch_detect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ directory: dirPath, chinese_redraw: chineseRedraw })
        });
        const data = await response.json();
        
        if (data.success) {
            // 切换到批量网格显示
            switchTab('batch');
            
            // 渲染网格列表
            const gridContainer = document.getElementById('batch-grid');
            gridContainer.innerHTML = '';
            
            STATE.batchResults = {}; // 清空缓存
            
            data.results.forEach(res => {
                // 保存数据供弹窗调用
                STATE.batchResults[res.filename] = res;
                
                const card = document.createElement('div');
                card.className = 'grid-card';
                card.onclick = () => openImageModal(res.filename);
                
                const defectCount = res.detections.length;
                const countBadge = defectCount > 0 ? `<div class="badge-defect-count">${defectCount}</div>` : '';
                
                card.innerHTML = `
                    <div class="grid-card-img-wrapper">
                        <img src="${res.result_url}?t=${Date.now()}" alt="${res.filename}">
                    </div>
                    ${countBadge}
                    <div class="grid-card-info">
                        <div class="grid-card-name" title="${res.filename}">${res.filename}</div>
                        <div class="grid-card-stats">
                            <span class="coord-text">${res.ms.toFixed(1)} ms</span>
                            <span style="color: ${defectCount > 0 ? 'var(--danger-color)' : 'var(--success-color)'}; font-weight:bold;">
                                ${defectCount > 0 ? '缺陷' : '正常'}
                            </span>
                        </div>
                    </div>
                `;
                gridContainer.appendChild(card);
            });
            
            // 更新统计指标为当前的批量数据总和
            STATE.totalFrames += data.summary.total_images;
            STATE.accumulatedMs += (data.summary.avg_ms * data.summary.total_images);
            STATE.totalDefects += data.summary.total_defects;
            
            KEYS_EN.forEach(key => {
                const cnName = EN_TO_CN[key];
                STATE.defectCounts[key] += (data.summary.defect_counts[cnName] || 0);
            });
            
            updateStatsUI();
            updateChart();
            
            // 更新顶栏指标
            document.getElementById('top-ms').textContent = data.summary.avg_ms.toFixed(1);
            document.getElementById('top-fps').textContent = 'N/A';
            
            // 更新主界面的检测明细表格（展示最后一张图的明细）
            if (data.results && data.results.length > 0) {
                const lastResult = data.results[data.results.length - 1];
                populateDetailTable(lastResult.detections);
            }
            
            showToast(`批量检测完成！共处理 ${data.summary.total_images} 张图片。`, 'success');
        } else {
            showToast(`批量检测失败: ${data.error}`, 'danger');
        }
    } catch (err) {
        showToast(`网络请求异常: ${err.message}`, 'danger');
    } finally {
        batchBtn.disabled = false;
        batchBtn.textContent = '开始批量处理';
    }
}

// ---------- 4. 双图比对弹窗控制 ----------
function openImageModal(filename) {
    const res = STATE.batchResults[filename];
    if (!res) return;
    
    // 加载图片
    document.getElementById('modal-img-original').src = `/api/get_original_image?path=${encodeURIComponent(res.original_path)}`;
    document.getElementById('modal-img-annotated').src = `${res.result_url}?t=${Date.now()}`;
    
    // 加载缺陷表格
    populateDetailTable(res.detections, 'modal-detail-table-body');
    
    // 显示弹窗
    document.getElementById('image-modal').style.display = 'flex';
}

function closeImageModal() {
    document.getElementById('image-modal').style.display = 'none';
}

// ---------- 5. 视图 Tab 切换 ----------
function switchTab(tabName) {
    const btnSingle = document.getElementById('tab-single');
    const btnBatch = document.getElementById('tab-batch');
    const paneSingle = document.getElementById('pane-single');
    const paneBatch = document.getElementById('pane-batch');
    
    if (tabName === 'single') {
        btnSingle.classList.add('active');
        btnBatch.classList.remove('active');
        paneSingle.classList.add('active');
        paneBatch.classList.remove('active');
    } else {
        btnSingle.classList.remove('active');
        btnBatch.classList.add('active');
        paneSingle.classList.remove('active');
        paneBatch.classList.add('active');
    }
}

// ---------- 6. 绑定 DOM 事件 ----------
document.addEventListener('DOMContentLoaded', () => {
    // 初始化 Chart.js
    initChart();
    
    // 检测系统状态
    checkSystemStatus();
    
    // 1. 单图上传事件
    const fileInput = document.getElementById('image-input');
    const selectBtn = document.getElementById('select-image-btn');
    const detectBtn = document.getElementById('detect-image-btn');
    const filenameText = document.getElementById('selected-filename');
    
    selectBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            filenameText.textContent = fileInput.files[0].name;
            detectBtn.disabled = false;
        } else {
            filenameText.textContent = '未选择文件';
            detectBtn.disabled = true;
        }
    });
    
    detectBtn.addEventListener('click', uploadAndDetectImage);
    
    // 2. 实时摄像头事件
    document.getElementById('start-camera-btn').addEventListener('click', startCamera);
    document.getElementById('stop-camera-btn').addEventListener('click', stopCamera);
    
    // 3. 批量检测事件
    document.getElementById('start-batch-btn').addEventListener('click', runBatchDetect);
    
    // 4. 重置统计与 Tab 切换
    document.getElementById('reset-stats-btn').addEventListener('click', resetStats);
    document.getElementById('tab-single').addEventListener('click', () => switchTab('single'));
    document.getElementById('tab-batch').addEventListener('click', () => switchTab('batch'));
    
    // 5. 弹窗关闭事件
    document.getElementById('modal-close').addEventListener('click', closeImageModal);
    document.getElementById('image-modal').addEventListener('click', (e) => {
        if (e.target.id === 'image-modal') closeImageModal();
    });
});
