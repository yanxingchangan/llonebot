import os
from typing import Dict, Any

class Config:
    # API配置，这里接入deepseek
    API_KEY = "your_api_key_here"
    API_ENDPOINT = "https://api.deepseek.com/user/balance"
    CHAT_ENDPOINT = "https://api.deepseek.com/chat/completions"
    
    # 系统配置
    ADMIN_ID = "your_admini_qq_id_here"
    target_group_id = "your_target_group_id_here"
    ADMIN_SERVER = "http://localhost:3000/send_msg"
    LOCAL_SERVER = "http://localhost:3000/send_group_msg"
    BILIBILI_COOKIE = "SESSDATA=; bili_jct=;"

    HISTORY_DIR = "./history"
    MAX_DUPLICATE_HOURS = 1
    
    # 特定用户预设
    USER_PRESETS = {
        ADMIN_ID: {
            "content": "You are a helpful assistant.",
            "role": "assistant"
        }
    }

    # 默认预设
    DEFAULT_PRESET = {
        "content": "You are a helpful assistant.",
        "role": "assistant"
    }
    
    # 媒体资源配置
    MEDIA = {
        "schedule_image": "http://example.com/schedule.jpg",
        "songs_images_1":r"file://E:/project/粥歌1.jpg",
        "songs_images_2":r"file://E:/project/粥歌2.jpg"
    }
    
    @classmethod
    def init(cls):
        os.makedirs(cls.HISTORY_DIR, exist_ok=True)