import httpx
import requests
import concurrent.futures
from typing import Optional, Dict, Any
from config import Config

class MessageHandler:
    def __init__(self):
        self.server_url = Config.LOCAL_SERVER
        self.private_url = Config.ADMIN_SERVER
    
    async def send_message(self, group_id:int, message: Dict[str, Any]) -> Optional[requests.Response]:
        """发送群普通消息"""
        def post_request():
            try:
                response = requests.post(self.server_url, json={
                    'group_id': group_id,
                    'message': message
                })
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                print(f"请求失败：{e}")
                return None

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(post_request)
            return future.result()
    
    async def send_group_message(self, group_id: int, user_id: str, message: str) -> Optional[requests.Response]:
        """发送群@消息"""
        message_payload = {
            "group_id": group_id,
            "message": [
                {
                    "type": "at",
                    "data": {
                        "qq": f"{user_id}",
                    }
                },
                {
                    "type": "text",
                    "data": {
                        "text": message
                    }
                }
            ]
        }
        try:
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.server_url,
                    json=message_payload,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                return response
        except Exception as e:
            print(f"发送群消息失败：{e}")
            return None
    
    async def send_private_message(self, user_id:int, messgae: Dict[str, Any]) -> Optional[httpx.Response]:
        """发送私聊消息"""
        def post_request():
            try:
                response = requests.post(self.private_url, json={
                    'user_id': user_id,
                    'message': messgae
                })
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                print(f"请求失败：{e}")
                return None

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(post_request)
            return future.result()