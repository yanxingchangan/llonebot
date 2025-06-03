import sqlite3
import base64
from datetime import datetime
from io import BytesIO
from PIL import Image
import numpy as np

class ImageDatabaseManager:
    """以 Base64 编码存储图片数据的 SQLite 数据库管理器"""
    
    def __init__(self, db_path: str = "image_data.db", similarity_threshold: float = 0.9):
        """
        初始化数据库连接并创建表
        :param db_path: 数据库文件路径
        :param similarity_threshold: 图片相似度阈值(0.0-1.0)，越高要求越相似
        """
        self.conn = sqlite3.connect(db_path)
        self.similarity_threshold = similarity_threshold
        self._create_table()

    def _create_table(self):
        """创建数据表（如果不存在）"""
        sql = """
        CREATE TABLE IF NOT EXISTS image_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_number TEXT NOT NULL,
            base64_data TEXT NOT NULL,
            perceptual_hash TEXT NOT NULL,
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_qq_number ON image_store (qq_number);
        CREATE INDEX IF NOT EXISTS idx_perceptual_hash ON image_store (perceptual_hash);
        """
        self.conn.executescript(sql)
        self.conn.commit()

    def _calculate_perceptual_hash(self, base64_data: str) -> str:
        """
        计算图片的感知哈希值（pHash算法）
        :param base64_data: 图片的Base64编码
        :return: 感知哈希值字符串
        """
        try:
            # 解码Base64数据
            img_data = base64.b64decode(base64_data.split(',')[-1] if ',' in base64_data else base64_data)
            img = Image.open(BytesIO(img_data))
            
            # 转为灰度图并缩放到8x8
            img = img.convert('L').resize((8, 8), Image.Resampling.LANCZOS)
            
            # 获取像素值并计算平均值
            pixels = np.array(img)
            avg_pixel = pixels.mean()
            
            # 生成64位哈希值（高于平均值记为1，否则为0）
            diff = pixels > avg_pixel
            # 将布尔数组转换为01字符串
            phash = ''.join('1' if x else '0' for x in diff.flatten())
            return phash
            
        except Exception as e:
            print(f"计算感知哈希失败: {e}")
            # 出错时返回全0哈希，确保不影响后续操作
            return '0' * 64

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        计算两个哈希值之间的汉明距离
        :return: 不同位的数量
        """
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    def _is_similar_image_exists(self, perceptual_hash: str) -> bool:
        """
        检查数据库中是否存在相似图片
        :param perceptual_hash: 待检查图片的感知哈希值
        :return: 是否存在相似图片
        """
        # 获取所有图片的感知哈希值
        cursor = self.conn.execute("SELECT perceptual_hash FROM image_store")
        stored_hashes = cursor.fetchall()
        
        hash_length = len(perceptual_hash)
        max_distance = int(hash_length * (1 - self.similarity_threshold))
        
        # 计算与现有图片的相似度
        for (stored_hash,) in stored_hashes:
            if self._hamming_distance(perceptual_hash, stored_hash) <= max_distance:
                return True
                
        return False

    def insert_image(self, qq_number: str, base64_data: str) -> bool:
        """
        插入图片数据（使用感知哈希检查相似性）
        :param qq_number: 用户QQ号
        :param base64_data: 图片的Base64编码字符串
        :return: True=插入成功, False=数据已存在或插入失败
        """
        try:
            # 计算感知哈希
            perceptual_hash = self._calculate_perceptual_hash(base64_data)
            
            # 检查是否存在相似图片
            if self._is_similar_image_exists(perceptual_hash):
                print("已存在相似图片，跳过插入")
                return False

            # 插入新数据
            sql = """
                INSERT INTO image_store (qq_number, base64_data, perceptual_hash)
                VALUES (?, ?, ?)
            """
            self.conn.execute(sql, (qq_number, base64_data, perceptual_hash))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"插入失败: {e}")
            return False
        except Exception as e:
            print(f"处理图片时发生错误: {e}")
            return False

    def get_images_by_qq(self, qq_number: str) -> list:
        """
        按QQ号查询所有关联的图片数据
        :param qq_number: 要查询的QQ号
        :return: 查询结果列表（按时间倒序）
        """
        try:
            sql = "SELECT * FROM image_store WHERE qq_number = ? ORDER BY upload_time DESC"
            cursor = self.conn.execute(sql, (qq_number,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"查询数据失败: {e}")
            return []

    def get_random_image(self) -> str | None:
        """
        随机获取一条图片的 Base64 数据
        :return: Base64 字符串（若无数据返回 None）
        """
        try:
            sql = """
                SELECT base64_data 
                FROM image_store 
                ORDER BY RANDOM() 
                LIMIT 1
            """
            cursor = self.conn.execute(sql)
            result = cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error as e:
            print(f"随机查询失败: {e}")
            return None
            
    def find_similar_images(self, base64_data: str, threshold: float = None) -> list:
        """
        查找与输入图片相似的所有图片
        :param base64_data: 图片的Base64编码字符串
        :param threshold: 可选的自定义阈值，不指定则使用实例默认值
        :return: 相似图片列表
        """
        if threshold is None:
            threshold = self.similarity_threshold
            
        try:
            # 计算输入图片的感知哈希
            query_hash = self._calculate_perceptual_hash(base64_data)
            hash_length = len(query_hash)
            max_distance = int(hash_length * (1 - threshold))
            
            # 获取所有图片哈希值
            cursor = self.conn.execute("SELECT id, qq_number, perceptual_hash FROM image_store")
            results = []
            
            for row in cursor.fetchall():
                id, qq, stored_hash = row
                distance = self._hamming_distance(query_hash, stored_hash)
                similarity = 1 - (distance / hash_length)
                
                if distance <= max_distance:
                    results.append({
                        "id": id,
                        "qq_number": qq,
                        "similarity": similarity
                    })
            
            # 按相似度降序排序
            return sorted(results, key=lambda x: x["similarity"], reverse=True)
            
        except Exception as e:
            print(f"查找相似图片失败: {e}")
            return []

    def close(self):
        """关闭数据库连接"""
        self.conn.close()