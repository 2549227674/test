# -*- coding: utf-8 -*-
import os
from PIL import Image

def check_images(dir_path):
    print(f"开始检查目录: {dir_path}")
    if not os.path.exists(dir_path):
        print(f"错误: 目录 {dir_path} 不存在")
        return
        
    files = sorted(os.listdir(dir_path))
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    
    total = 0
    corrupted = 0
    valid = 0
    
    for f in files:
        if not f.lower().endswith(image_extensions):
            continue
            
        total += 1
        file_path = os.path.join(dir_path, f)
        
        try:
            # 检查文件大小
            size_bytes = os.path.getsize(file_path)
            if size_bytes == 0:
                print(f"[损坏] {f} - 文件大小为 0 字节 (需要修复)")
                corrupted += 1
                continue
                
            # 尝试使用 PIL 打开并验证图像
            with Image.open(file_path) as img:
                img.verify()  # verify checks if the file is broken without loading pixel data
            
            # 再试着真实加载图像以确保完全完好
            with Image.open(file_path) as img:
                img.load()
                w, h = img.size
                valid += 1
        except Exception as e:
            print(f"[损坏] {f} - 图像解码失败: {str(e)} (需要修复)")
            corrupted += 1
            
    print("\n========== 检查总结 ==========")
    print(f"总图片数: {total}")
    print(f"有效图片数: {valid}")
    print(f"损坏/需修复数: {corrupted}")
    if corrupted > 0:
        print("结论: 发现部分图片损坏，需要修复！")
    else:
        print("结论: 所有图片均完整有效，无需修复。")

if __name__ == '__main__':
    import sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        test_images_dir = sys.argv[1]
    else:
        test_images_dir = os.path.join(HERE, "test_images")
    check_images(test_images_dir)
