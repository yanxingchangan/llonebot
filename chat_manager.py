import json
import httpx
import logging
import random
import pandas as pd
import requests
import time
from typing import Dict, Tuple, Any
from config import Config

class ChatManager:
    def __init__(self):
        self.sessions: Dict[int, list] = {}
        self.session_timestamps: Dict[int, float] = {}
        self.session_timeout = Config.SESSION_TIMEOUT if hasattr(Config, 'SESSION_TIMEOUT') else 1800
        
    def get_fresh_session(self, user_id: int) -> list:
        """获取一个新的会话"""
        preset = Config.USER_PRESETS.get(user_id, Config.DEFAULT_PRESET)
        self.sessions[user_id] = [preset.copy()]
        self.session_timestamps[user_id] = time.time()
        return self.sessions[user_id]
    
    def add_message(self, user_id: int, message: str, role: str):
        """添加消息到当前会话"""
        session = self.get_fresh_session(user_id)
        session.append({"content": message, "role": role})
        
    async def get_chat_response(self, user_id: int, message: str) -> Tuple[int, str]:
        """获取AI响应"""
        self.clean_expired_sessions()
        self.add_message(user_id, message, "user")
        session = self.sessions[user_id]
        
        payload = {
            "messages": session,
            "model": "deepseek-chat",
            "max_tokens": 2048,
            "temperature": 1,
            "top_p": 1
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {Config.API_KEY}'
        }

        try:
            response = requests.post(
                Config.CHAT_ENDPOINT, 
                headers=headers, 
                json=payload
            )
            response.raise_for_status()
            
            response_json = response.json()
            if "choices" not in response_json or not response_json["choices"]:
                return response.status_code, "响应缺少有效的 'choices' 字段"
            
            bot_reply = response_json["choices"][0]["message"]["content"]
            
            self.end_chat(user_id)
            
            return response.status_code, bot_reply
            
        except Exception as e:
            logging.error(f"Chat请求错误: {str(e)}")
            self.end_chat(user_id)
            return 500, f"请求错误: {str(e)}"
    
    def clean_expired_sessions(self):
        """清理过期的会话"""
        current_time = time.time()
        expired_users = [
            user_id for user_id, timestamp in self.session_timestamps.items()
            if current_time - timestamp > self.session_timeout
        ]
        
        for user_id in expired_users:
            self.end_chat(user_id)
            
    def get_random_video(self) -> Dict[str, Any]:
        """获取随机视频"""
        filename = "up_videos.xlsx"
        try:
            df = pd.read_excel(filename)
            non_empty_cells = [(i, j) for i in range(df.shape[0]) for j in range(df.shape[1]) if pd.notnull(df.iat[i, j])]
            if not non_empty_cells:
                logging.warning("文件中没有非空单元格。")
                return None
            random_cell = random.choice(non_empty_cells)
            row, col = random_cell
            cell_value = df.iat[row, col]
            return cell_value
        except Exception as e:
            logging.error(f"获取随机视频失败: {str(e)}")
            return None
    
    async def get_balance(self) -> str:
        """获取API账户余额"""
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {Config.API_KEY}'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(Config.API_ENDPOINT, headers=headers)
                response.raise_for_status()
                data = response.json()

                if not data.get("is_available"):
                    return "API服务不可用"

                balance_info = data.get("balance_infos", [])
                if not balance_info:
                    return "无可用余额信息"
                    
                balance = balance_info[0].get("total_balance")
                if balance is None:
                    return "余额信息无效"
                    
                return f"{balance:.2f}"

        except Exception as e:
            logging.error(f"获取余额错误: {str(e)}")
            return f"查询失败: {str(e)}"
            
    def end_chat(self, user_id: int):
        """结束并清除用户会话"""
        if user_id in self.sessions:
            del self.sessions[user_id]
        if user_id in self.session_timestamps:
            del self.session_timestamps[user_id]
        logging.info(f"已结束用户 {user_id} 的会话")