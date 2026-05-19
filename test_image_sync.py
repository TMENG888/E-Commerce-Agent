import os
import sys
import time
import shutil

sys.path.insert(0, 'c:/Users/31193/PycharmProjects/playwright__e-commerce')

from mobile_image_sync import MobileImageSync
from config import ip_port

def test_image_sync():
    """测试图片同步功能"""
    
    print("=" * 60)
    print("🧪 测试图片同步功能")
    print("=" * 60)
    
    # 创建同步器
    sync = MobileImageSync(ip_port)
    
    # 测试1: 连接设备
    print("\n📱 测试1: 连接设备")
    if sync.connect_device():
        print("✅ 设备连接成功")
    else:
        print("❌ 设备连接失败")
        return
    
    # 测试2: 获取手机目录文件列表
    print("\n📂 测试2: 获取手机目录文件列表")
    files = sync.get_phone_files("/storage/emulated/0/DCIM/Pindd/save_image")
    print(f"手机目录文件: {files}")
    
    # 测试3: 如果有文件，同步最新的一张
    if files:
        print("\n🔄 测试3: 同步最新图片")
        
        # 过滤图片文件，最后一个就是最新的
        image_files = [f for f in files if f.endswith('.jpg') or f.endswith('.png')]
        
        if not image_files:
            print("⚠️ 未找到图片文件")
            return
        
        # 直接取最后一个文件（最新的）
        newest_file = image_files[-1]
        print(f"找到最新文件: {newest_file}")
        
        if newest_file:
            print(f"找到最新文件: {newest_file}")
            
            # 创建测试目录
            test_dir = r"C:\Users\31193\Pictures\商品规格图\test_sync"
            os.makedirs(test_dir, exist_ok=True)
            
            # 下载文件
            phone_path = os.path.join("/storage/emulated/0/DCIM/Pindd/save_image", newest_file)
            temp_path = os.path.join(test_dir, f"temp_{newest_file}")
            
            print(f"📥 准备下载: {phone_path} -> {temp_path}")
            
            if sync.download_file(phone_path, temp_path):
                # 检查下载的是文件还是文件夹
                if os.path.isdir(temp_path):
                    print(f"⚠️ 下载结果是文件夹，检查目录内容:")
                    for item in os.listdir(temp_path):
                        print(f"   - {item}")
                        # 如果文件夹里有文件，移动出来
                        item_path = os.path.join(temp_path, item)
                        if os.path.isfile(item_path):
                            final_path = os.path.join(test_dir, f"test_{int(time.time())}.jpg")
                            shutil.move(item_path, final_path)
                            print(f"✅ 测试成功！图片已保存到: {final_path}")
                            # 删除空文件夹
                            os.rmdir(temp_path)
                elif os.path.isfile(temp_path):
                    # 重命名
                    final_path = os.path.join(test_dir, f"test_{int(time.time())}.jpg")
                    shutil.move(temp_path, final_path)
                    print(f"✅ 测试成功！图片已保存到: {final_path}")
                else:
                    print(f"❌ 下载结果既不是文件也不是文件夹")
                
                # 询问是否删除手机端文件
                delete = input("是否删除手机端该图片? (y/n): ")
                if delete.lower() == 'y':
                    if sync.delete_phone_file(phone_path):
                        print(f"✅ 已删除手机端图片: {newest_file}")
                    else:
                        print("❌ 删除失败")
        else:
            print("⚠️ 未找到图片文件")
    else:
        print("⚠️ 手机目录为空，请先保存一张图片")
    
    print("\n" + "=" * 60)
    print("🎯 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_image_sync()