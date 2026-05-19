import os
import time
import shutil
import hashlib
import threading
import uiautomator2 as u2
from datetime import datetime


class MobileImageSync:
    def __init__(self, ip_port):
        self.ip_port = ip_port
        self.phone_pdd_dir = "/storage/emulated/0/DCIM/Pindd/save_image"
        self.computer_base_dir = r"C:\Users\31193\Pictures\商品规格图"
        
        self.synced_files = set()
        self.device = None
        
    def connect_device(self):
        """连接设备"""
        if not self.device:
            try:
                self.device = u2.connect(self.ip_port)
                print(f"✅ 已连接设备: {self.ip_port}")
                return True
            except Exception as e:
                print(f"❌ 连接设备失败: {e}")
                return False
        return True
    
    def get_phone_files(self, phone_dir):
        """获取手机上指定目录的文件列表（使用 uiautomator2 shell）"""
        if not self.connect_device():
            return []
        
        try:
            result = self.device.shell(f"ls -1 {phone_dir}")
            output = result.output if hasattr(result, 'output') else str(result)
            files = [f.strip() for f in output.strip().split('\n') if f.strip() and not f.startswith('.')]
            print(f"📂 手机目录 {phone_dir} 中的文件: {files}")
            return files
        except Exception as e:
            print(f"❌ 获取手机文件列表失败: {e}")
            return []
    
    def download_file(self, phone_path, computer_path):
        """从手机下载文件到电脑（使用 uiautomator2 pull）"""
        if not self.connect_device():
            return False
        
        try:
            # 删除可能存在的同名文件或文件夹
            if os.path.exists(computer_path):
                if os.path.isdir(computer_path):
                    import shutil
                    shutil.rmtree(computer_path)
                else:
                    os.remove(computer_path)
            
            # 修复路径分隔符：Android 需要正斜杠
            phone_path = phone_path.replace('\\', '/')
            print(f"🔧 执行 pull: {phone_path} -> {computer_path}")
            result = self.device.pull(phone_path, computer_path)
            print(f"🔧 pull 返回结果: {result}")
            
            # 调试：检查目标位置
            if os.path.exists(computer_path):
                if os.path.isdir(computer_path):
                    print(f"⚠️ 下载结果是文件夹")
                    contents = os.listdir(computer_path)
                    print(f"⚠️ 文件夹内容: {contents}")
                    # 检查文件夹里是否有文件
                    files_in_dir = [f for f in os.listdir(computer_path) if os.path.isfile(os.path.join(computer_path, f))]
                    if files_in_dir:
                        print(f"✅ 文件夹中有文件: {files_in_dir}")
                        # 取第一个文件
                        inner_file = os.path.join(computer_path, files_in_dir[0])
                        # 移动文件到正确位置
                        new_path = computer_path + ".tmp"
                        os.rename(computer_path, new_path)
                        os.rename(inner_file, computer_path)
                        # 删除空文件夹
                        import shutil
                        shutil.rmtree(new_path)
                elif os.path.isfile(computer_path):
                    print(f"✅ 下载结果是文件，大小: {os.path.getsize(computer_path)} bytes")
            
            if os.path.isfile(computer_path):
                print(f"✅ 下载成功: {phone_path} -> {computer_path}")
                return True
            else:
                print(f"❌ 下载结果不是文件")
                # 尝试使用 adb pull 命令
                print("🔄 尝试使用 adb pull 命令...")
                return self._download_with_adb(phone_path, computer_path)
                
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            # 尝试使用 adb pull 命令
            print("🔄 尝试使用 adb pull 命令...")
            return self._download_with_adb(phone_path, computer_path)
    
    def _download_with_adb(self, phone_path, computer_path):
        """使用 adb 命令下载文件（备用方法）"""
        try:
            import subprocess
            
            # 删除可能存在的同名文件或文件夹
            if os.path.exists(computer_path):
                if os.path.isdir(computer_path):
                    import shutil
                    shutil.rmtree(computer_path)
                else:
                    os.remove(computer_path)
            
            # 修复路径分隔符：Android 需要正斜杠
            phone_path = phone_path.replace('\\', '/')
            cmd = f"adb -s {self.ip_port} pull \"{phone_path}\" \"{computer_path}\""
            print(f"🔧 执行命令: {cmd}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            print(f"🔧 命令返回码: {result.returncode}")
            if result.stdout:
                print(f"🔧 命令输出: {result.stdout}")
            if result.stderr:
                print(f"🔧 命令错误: {result.stderr}")
            
            if os.path.isfile(computer_path):
                print(f"✅ adb 下载成功: {phone_path} -> {computer_path}")
                return True
            else:
                print(f"❌ adb 下载结果不是文件")
                return False
                
        except Exception as e:
            print(f"❌ adb 下载失败: {e}")
            return False
    
    def delete_phone_file(self, phone_path):
        """删除手机上的文件"""
        if not self.connect_device():
            return False
        
        try:
            self.device.shell(f"rm {phone_path}")
            return True
        except Exception as e:
            print(f"❌ 删除失败: {e}")
            return False
    
    def get_file_hash(self, file_path):
        """计算文件哈希值用于去重"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None
    
    def sync_images_for_goods(self, goods_id, specs, timeout=60):
        """
        同步指定商品的图片
        goods_id: 商品ID
        specs: 规格字典 {"规格名": 价格}
        timeout: 等待超时时间（秒）
        """
        print(f"\n🔄 开始同步商品 {goods_id} 的图片...")
        
        target_dir = os.path.join(self.computer_base_dir, str(goods_id))
        os.makedirs(target_dir, exist_ok=True)
        
        spec_names = list(specs.keys())
        downloaded_count = 0
        start_time = time.time()
        
        existing_files = set()
        
        while downloaded_count < len(spec_names) and (time.time() - start_time) < timeout:
            pdd_files = self.get_phone_files(self.phone_pdd_dir)
            
            for filename in pdd_files:
                if filename.endswith('.jpg') or filename.endswith('.png'):
                    phone_path = os.path.join(self.phone_pdd_dir, filename)
                    
                    if filename in existing_files:
                        continue
                    existing_files.add(filename)
                    
                    temp_path = os.path.join(target_dir, f"temp_{filename}")
                    if self.download_file(phone_path, temp_path):
                        file_hash = self.get_file_hash(temp_path)
                        if file_hash and file_hash not in self.synced_files:
                            self.synced_files.add(file_hash)
                            
                            if downloaded_count < len(spec_names):
                                spec_name = spec_names[downloaded_count]
                                clean_name = spec_name.replace('/', '_').replace('\\', '_').replace(':', '_')
                                final_path = os.path.join(target_dir, f"{clean_name}.jpg")
                                
                                if os.path.exists(final_path):
                                    base, ext = os.path.splitext(final_path)
                                    final_path = f"{base}_{int(time.time())}{ext}"
                                
                                shutil.move(temp_path, final_path)
                                print(f"📝 重命名为规格名: {final_path}")
                                downloaded_count += 1
                            else:
                                os.remove(temp_path)
                
            time.sleep(2)
        
        if downloaded_count >= len(spec_names):
            print(f"✅ 成功同步 {downloaded_count} 张图片")
        else:
            print(f"⏰ 超时，已同步 {downloaded_count}/{len(spec_names)} 张图片")
        
        return downloaded_count
    
    def sync_single_spec_image(self, goods_id, spec_name, async_mode=True, sku_data_map=None):
        """
        同步单张图片（边采集边同步，确保图片与规格一一对应）
        goods_id: 商品ID
        spec_name: 规格名称（用于命名图片）
        async_mode: 是否异步执行（默认True，不阻塞主线程）
        sku_data_map: 可选的规格数据字典，用于更新 path 字段
        """
        if async_mode:
            thread = threading.Thread(
                target=self._sync_single_spec_image_sync,
                args=(goods_id, spec_name, sku_data_map),
                daemon=True
            )
            thread.start()
            print(f"🔄 启动异步同步线程: {spec_name}")
        else:
            self._sync_single_spec_image_sync(goods_id, spec_name, sku_data_map)
    
    def _sync_single_spec_image_sync(self, goods_id, spec_name, sku_data_map=None):
        """同步版本：实际执行图片同步"""
        target_dir = os.path.join(self.computer_base_dir, str(goods_id))
        os.makedirs(target_dir, exist_ok=True)
        
        clean_name = spec_name.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
        final_path = os.path.join(target_dir, f"{clean_name}.jpg")
        
        if os.path.exists(final_path):
            base, ext = os.path.splitext(final_path)
            final_path = f"{base}_{int(time.time())}{ext}"
        
        time.sleep(1.5)
        
        pdd_files = self.get_phone_files(self.phone_pdd_dir)
        
        # 过滤出图片文件，排除已同步过的文件
        image_files = [f for f in pdd_files if (f.endswith('.jpg') or f.endswith('.png')) and f not in self.synced_files]
        
        if not image_files:
            print(f"⚠️ 未找到新图片用于规格: {spec_name}")
            return
        
        # 直接取最后一个文件（最新的）
        newest_file = image_files[-1]
        print(f"🔍 找到最新图片: {newest_file}")
        
        phone_path = os.path.join(self.phone_pdd_dir, newest_file)
        temp_path = os.path.join(target_dir, f"temp_{newest_file}")
        
        if self.download_file(phone_path, temp_path):
            shutil.move(temp_path, final_path)
            print(f"✅ 同步图片: {spec_name} -> {final_path}")
            
            # 标记为已同步
            self.synced_files.add(newest_file)
            
            # 更新 sku_data_map 中的 path 字段
            if sku_data_map and spec_name in sku_data_map:
                sku_data_map[spec_name]["path"] = final_path
                print(f"✅ 更新 sku_data_map: {spec_name} -> path = {final_path}")
            
            # 保存图片路径到 MongoDB
            self._save_image_path_to_mongo(goods_id, spec_name, final_path)
            
            if self.delete_phone_file(phone_path):
                print(f"🧹 已删除手机端图片: {newest_file}")
            else:
                print(f"⚠️ 删除手机端图片失败")
        else:
            print(f"❌ 下载图片失败: {newest_file}")
    
    def _save_image_path_to_mongo(self, goods_id, spec_name, image_path):
        """保存图片路径到 MongoDB（需要在调用处导入 add_sku_item）"""
        try:
            # 动态导入以避免循环依赖
            from collect_data.pdd.uiautomator2_spider.uiautomator2_to_db.uiautomator2_url_spider_backup import add_sku_item
            
            # 从 MongoDB 获取当前商品的规格数量
            from pymongo import MongoClient
            client = MongoClient("localhost", 27017)
            col = client["Goofish"]["Goods_Specification"]
            doc = col.find_one({"_id": goods_id})
            
            # 计算新的 spec_id
            spec_id = 1
            if doc and "sku" in doc:
                spec_id = len(doc["sku"]) + 1
            
            # 获取价格（需要从临时存储中获取）
            price = 0.0  # 实际应该从 sku_data_map 中获取
            
            add_sku_item(goods_id, spec_name, price, image_path, spec_id)
            print(f"✅ 已保存图片路径到 MongoDB: {spec_name} -> {image_path}")
        except Exception as e:
            print(f"❌ 保存图片路径到 MongoDB 失败: {e}")
    
    def clear_phone_pdd_images(self):
        """清理拼多多保存的图片目录"""
        if not self.connect_device():
            return
        
        try:
            self.device.shell(f"rm -rf {self.phone_pdd_dir}/*")
            print("🧹 已清理手机拼多多图片")
        except Exception as e:
            print(f"❌ 清理手机图片失败: {e}")