from config import Config
from auth_manager import AuthManager
from message_handler import MessageHandler
from chat_manager import ChatManager
from ImageDatabaseManager import ImageDatabaseManager
from fastapi import FastAPI, Request
import uvicorn
import logging
import httpx
import psutil
import time
import asyncio
import threading
from collections import defaultdict
import httpx
import base64
import io

# 初始化配置和日志
Config.init()
logging.basicConfig(
    filename='group_chat_system.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 定时问候配置
greeting = {
    "07:00": r"file://E:/project/get up.wav",
    "02:00": r"file://E:/project/good night.wav",
}

# 令牌桶实现
class TokenBucket:
    """令牌桶限流算法实现"""
    def __init__(self, capacity, fill_rate):
        """
        初始化令牌桶
        :param capacity: 桶的容量
        :param fill_rate: 令牌填充速率(每秒)
        """
        self.capacity = capacity  # 桶的容量
        self.tokens = capacity    # 当前令牌数量
        self.fill_rate = fill_rate  # 填充速率
        self.last_time = time.time()  # 上次请求时间
    
    def consume(self, tokens=1):
        """
        消耗令牌
        :param tokens: 需要消耗的令牌数
        :return: 如果可以消耗则返回True，否则返回False
        """
        # 首先添加新令牌
        now = time.time()
        time_passed = now - self.last_time
        self.last_time = now
        
        # 添加新令牌
        self.tokens += time_passed * self.fill_rate
        if self.tokens > self.capacity:
            self.tokens = self.capacity
            
        # 检查是否有足够令牌可供消费
        if tokens <= self.tokens:
            self.tokens -= tokens
            return True
        return False

# 全局令牌桶限流器
chat_limiter = TokenBucket(5, 5)  # 每秒5个请求，最多积累5个令牌
video_limiter = TokenBucket(10, 3)  # 每秒3个视频请求，最多积累10个令牌

# 限流器
user_chat_limiters = {}
user_video_limiters = {}

# 数据库授权列表
EXEMPT_USERS = {Config.ADMIN_ID}

# 消息处理工具类
class MessageUtil:
    """消息处理工具类，封装各种消息发送模式"""
    
    def __init__(self, message_handler):
        self.message_handler = message_handler
    
    async def send_text(self, target_id, text, is_private=False, user_id=None):
        """发送文本消息"""
        try:
            if is_private:
                await self.message_handler.send_private_message(target_id, text)
            elif user_id:  # 群@ 消息
                await self.message_handler.send_group_message(target_id, user_id, text)
            else:  # 群普通消息
                await self.message_handler.send_message(
                    target_id,
                    {'type': 'text', 'data': {'text': text}}
                )
        except Exception as e:
            logging.error(f"发送文本消息失败: {e}")
    
    async def send_image(self, target_id, image_url=None, image_file=None, image_base=None, is_private=False):
        """发送图片消息"""
        try:
            image_data = {}
            if image_url:
                image_data['url'] = image_url
            elif image_file:
                image_data['file'] = image_file
            elif image_base:
                image_data['file'] = "base64://" + image_base
            message = {'type': 'image', 'data': image_data}
            
            if is_private:
                await self.message_handler.send_private_message(target_id, message)
            else:
                await self.message_handler.send_message(target_id, message)
        except Exception as e:
            logging.error(f"发送图片消息失败: {e}")
    
    async def send_video_recommendation(self, target_id, video_data, is_private=False):
        """发送视频推荐信息"""
        try:
            title = video_data.get('title', '无标题')
            cover_url = video_data.get('cover_url', '')
            jump_url = video_data.get('jump_url', '')
            
            videos = [
                    {
                        'type': 'text',
                        'data': {
                            'text': (
                                f"要睡觉了吗？那就让小粥哄哥哥吧\n"
                                f"-------------------------------------\n"
                                f"视频标题：{title}\n"
                            )
                        }
                    },
                    {
                        'type': 'image',
                        'data': {
                            'url': cover_url
                        }
                    },
                    {
                        'type': 'text',
                        'data': {
                            'text': f"视频链接：{jump_url}"
                        }
                    }
                ]

            if is_private:
                await self.message_handler.send_private_message(
                    target_id, 
                    videos
                )
            else:
                await self.message_handler.send_message(
                    target_id,
                    videos
                )
        except Exception as e:
            logging.error(f"发送视频推荐失败: {e}")
            if is_private:
                await self.message_handler.send_private_message(
                    target_id, 
                    f"发送视频失败: {str(e)}"
                )
            else:
                await self.message_handler.send_message(
                    target_id,
                    {'type': 'text', 'data': {'text': f"发送视频失败: {str(e)}"}}
                )

    async def send_message(self, target_id, message, is_private=False):
        """发送消息"""
        try:
            if is_private:
                await self.message_handler.send_private_message(target_id, message)
            else:
                await self.message_handler.send_message(target_id, message)
        except Exception as e:
            logging.error(f"发送消息失败: {e}")

# 速率限制检查
def rate_limit(limiter, user_limiters, user_id, exempt_users=None):
    """
    速率限制检查
    :param limiter: 全局限流器
    :param user_limiters: 用户级限流器字典
    :param user_id: 当前用户ID
    :param exempt_users: 豁免用户列表
    :return: (是否允许请求, 拒绝原因)
    """
    # 检查用户豁免
    if exempt_users and user_id in exempt_users:
        return True, ""
    
    # 全局限流检查
    if not limiter.consume(1):
        return False, "系统繁忙，请稍后再试"
    
    # 用户级限流器
    if user_id not in user_limiters:
        user_limiters[user_id] = TokenBucket(3, 0.5)
        user_limiters[user_id].tokens = 1
    
    # 用户级限流检查
    if not user_limiters[user_id].consume(1):
        return False, "请求太频繁，请稍后再试"
    
    return True, ""

# 从消息中提取图片URL
async def extract_image_urls(message_array):
    """
    从消息数组中提取所有图片的URL
    :param message_array: 消息数组
    :return: 图片URL列表
    """
    image_urls = []
    
    if not message_array:
        return image_urls
    
    for segment in message_array:
        if segment.get('type') == 'image':
            url = segment.get('data', {}).get('url')
            if url:
                image_urls.append(url)
    
    return image_urls

# url_to_base64 函数
async def url_to_base64(url):
    """将图片URL转换为Base64编码"""
    try:
        import subprocess
        import os
        import tempfile
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                temp_path = tmp.name
            
            curl_cmd = f'curl -k -A "Mozilla/5.0" -o "{temp_path}" "{url}"'
            subprocess.run(curl_cmd, shell=True, timeout=30)
            
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, "rb") as f:
                    image_data = f.read()
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                os.unlink(temp_path)
                return base64_data
        except Exception as e:
            logging.error(f"使用curl下载图片失败: {str(e)}")
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
        
        logging.error("获取图片失败")
        return None
        
    except Exception as e:
        logging.error(f"URL转Base64全局异常: {str(e)}")
        return None
    
# 初始化应用组件
app = FastAPI()
auth_manager = AuthManager(admin_id=Config.ADMIN_ID)
message_handler = MessageHandler()
chat_manager = ChatManager()
msg_util = MessageUtil(message_handler)
image_db = ImageDatabaseManager()

async def extract_at_content(raw_message, message_array):
    """提取@消息的内容"""
    is_at_bot = False
    actual_content = raw_message
    bot_qq = Config.BOT_ID
    
    # 方法1: 检查raw_message
    if raw_message.startswith(f"[CQ:at,qq={bot_qq}"):
        is_at_bot = True
        at_end_index = raw_message.find(']')
        if (at_end_index > 0):
            actual_content = raw_message[at_end_index+1:].strip()
        else:
            actual_content = ""
    
    # 方法2: 检查message数组
    elif message_array and len(message_array) > 0:
        first_segment = message_array[0]
        if (first_segment.get('type') == 'at' and 
            first_segment.get('data', {}).get('qq') == bot_qq):
            is_at_bot = True
            # 如果有多个消息段，提取文本内容
            actual_content = ""
            for segment in message_array[1:]:
                if segment.get('type') == 'text':
                    actual_content += segment.get('data', {}).get('text', '')
            actual_content = actual_content.strip()
    
    # 如果消息内容为空，设置默认值
    if is_at_bot and not actual_content:
        actual_content = "你好"
        
    return is_at_bot, actual_content

async def handle_at_message(user_id, group_id, content, message_array=None):
    """处理@消息"""
    try:
        # 应用限流
        allowed, reason = rate_limit(
            chat_limiter, 
            user_chat_limiters, 
            user_id,
            EXEMPT_USERS
        )
        
        if not allowed:
            await msg_util.send_text(
                group_id,
                reason,
                is_private=False,
                user_id=str(user_id)
            )
            return {}
        
        # 检测是否有图片消息
        has_image = False
        if message_array:
            if user_id not in EXEMPT_USERS:
                # 限制非管理员用户的图片消息
                for segment in message_array:
                    if segment.get('type') == 'image':
                        await msg_util.send_text(
                            group_id,
                            "无数据库写入权限",
                            is_private=False,
                            user_id=str(user_id)
                        )
                        return {}
            # 提取所有图片URL
            image_urls = []
            for segment in message_array:
                if segment.get('type') == 'image':
                    url = segment.get('data', {}).get('url')
                    if url:
                        image_urls.append(url)
                        has_image = True

        # 如果有图片，则处理图片并返回结果
        if has_image:
            image_count = 0
            for url in image_urls:
                logging.info(f"处理图片URL: {url}")
                # 转换图片为Base64
                base64_data = await url_to_base64(url)
                if base64_data:
                    # 保存到数据库
                    result = image_db.insert_image(str(user_id), base64_data)
                    if result:
                        image_count += 1
                        logging.info(f"成功保存用户 {user_id} 的图片到数据库")
                    else:
                        logging.info(f"图片已存在或保存失败，用户: {user_id}")
            # 回复保存结果
            if image_count > 0:
                await msg_util.send_text(
                    group_id,
                    f"已成功保存 {image_count} 张图片",
                    is_private=False,
                    user_id=str(user_id)
                )
            else:
                await msg_util.send_text(
                    group_id,
                    "图片保存失败或已存在",
                    is_private=False,
                    user_id=str(user_id)
                    )
            return {}
            

        # 获取AI响应
        code, answer = await chat_manager.get_chat_response(user_id, content)
            
        if code != 200:
            logging.error(f"AI响应错误: {code}, {answer}")
            await msg_util.send_text(
                Config.ADMIN_ID,
                f"用户 {user_id} 请求出错: {answer}",
                is_private=True
            )
            return {}
            
        # 发送回复
        await msg_util.send_text(
            group_id,
            answer,
            is_private=False,
            user_id=str(user_id)
        )
        
        return {}
    except Exception as e:
        logging.error(f"处理@消息时发生错误: {str(e)}")
        await msg_util.send_text(
            group_id,
            f"处理消息时出现错误，请稍后再试",
            is_private=False,
            user_id=str(user_id)
        )
        return {}

async def handle_video_request(target_id, is_private=False, user_id=None):
    """处理视频请求"""
    try:
        # 群聊模式需要限流检查
        if not is_private:
            if not video_limiter.consume(1):
                await msg_util.send_text(
                    target_id,
                    "系统繁忙，请稍后再试",
                    is_private
                )
                return {}
        
        bvs = chat_manager.get_random_video()
        if not bvs:
            await msg_util.send_text(
                target_id,
                "抱歉，未找到可推荐的视频",
                is_private
            )
            return {}
        
        # 获取视频信息
        video_data = await fetch_video_info(bvs)
        if not video_data:
            await msg_util.send_text(
                target_id,
                "获取视频信息失败",
                is_private
            )
            return {}
        
        # 发送视频信息
        await msg_util.send_video_recommendation(target_id, video_data, is_private)
        return {}
        
    except Exception as e:
        logging.error(f"处理视频请求时发生错误: {str(e)}")
        await msg_util.send_text(
            target_id,
            f"获取视频推荐失败: {str(e)}",
            is_private
        )
        return {}

async def fetch_video_info(bvid):
    """获取视频信息"""
    try:
        videos_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Cookie": Config.BILIBILI_COOKIE
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(videos_url, headers=headers, timeout=10.0)
        
        if response.status_code != 200:
            logging.error(f"获取视频信息失败: 状态码 {response.status_code}")
            return None

        data = response.json()
        items = data.get('data', {})
        
        return {
            'title': items.get('title', '无标题'),
            'cover_url': items.get('pic', ''),
            'jump_url': f"https://www.bilibili.com/video/{bvid}"
        }
    except Exception as e:
        logging.error(f"获取视频信息出错: {str(e)}")
        return None

async def handle_private_chat(user_id, message, message_array=None):
    """处理私聊聊天"""
    try:
        # 先检查用户是否有授权
        if not auth_manager.is_authorized(user_id):
            await msg_util.send_text(
                user_id,
                "您尚未获取授权，请先获取授权",
                is_private=True
            )
            return {}
        
        # 应用限流
        allowed, reason = rate_limit(
            chat_limiter, 
            user_chat_limiters, 
            user_id,
            EXEMPT_USERS
        )
        
        if not allowed:
            await msg_util.send_text(user_id, reason, is_private=True)
            return {}
        
        # 检测是否有图片消息
        has_image = False
        if message_array:
            # 提取所有图片URL
            image_urls = []
            for segment in message_array:
                if segment.get('type') == 'image':
                    url = segment.get('data', {}).get('url')
                    if url:
                        image_urls.append(url)
                        has_image = True

            # 如果有图片，则处理图片并返回结果
            if has_image:
                image_count = 0
                for url in image_urls:
                    logging.info(f"处理私聊图片URL: {url}")
                    # 转换图片为Base64
                    base64_data = await url_to_base64(url)
                    if base64_data:
                        # 保存到数据库
                        result = image_db.insert_image(str(user_id), base64_data)
                        if result:
                            image_count += 1
                            logging.info(f"成功保存用户 {user_id} 的图片到数据库")
                        else:
                            logging.info(f"图片已存在或保存失败，用户: {user_id}")
                # 回复保存结果
                if image_count > 0:
                    await msg_util.send_text(
                        user_id,
                        f"已成功保存 {image_count} 张图片",
                        is_private=True
                    )
                else:
                    await msg_util.send_text(
                        user_id,
                        "图片保存失败或已存在",
                        is_private=True
                    )
                return {}

        # 获取AI回复
        code, answer = await chat_manager.get_chat_response(user_id, message)
        
        if code != 200:
            logging.error(f"私聊AI响应错误: {code}, {answer}")
            await msg_util.send_text(
                user_id,
                f"请求出错: {answer}",
                is_private=True
            )
            
            if code >= 500:
                await msg_util.send_text(
                    Config.ADMIN_ID,
                    f"严重错误: 用户 {user_id} 的请求失败: {answer}",
                    is_private=True
                )
            return {}
            
        await msg_util.send_text(user_id, answer, is_private=True)
        return {}
    except Exception as e:
        logging.error(f"处理私聊对话时发生错误: {str(e)}")
        await msg_util.send_text(
            user_id,
            "处理消息时出现错误，请稍后再试",
            is_private=True
        )
        return {}
    
async def handle_songs_images(target_id, is_private=False):
    """处理粥歌图片发送"""
    try:
        for image_key in ['songs_images_1', 'songs_images_2']:
            await msg_util.send_image(
                target_id,
                image_file=Config.MEDIA[image_key],
                is_private=is_private
            )
        logging.info(f"发送粥歌图片成功: {'私聊' if is_private else '群聊'}")
        return {}
    except Exception as e:
        logging.error(f"发送粥歌图片时发生错误: {str(e)}")
        await msg_util.send_text(
            target_id,
            f"发送图片失败: {str(e)}",
            is_private=is_private
        )
        return {}

async def handle_random_image(target_id, is_private=False):
    """从数据库随机获取并发送一张图片"""
    try:
        base64_data = image_db.get_random_image()
        
        if not base64_data:
            await msg_util.send_text(
                target_id,
                "暂无图片可以显示",
                is_private=is_private
            )
            return {}
        
        await msg_util.send_image(
            target_id,
            image_base=base64_data,
            is_private=is_private
        )
        logging.info(f"成功发送随机图片: {'私聊' if is_private else '群聊'}")
        return {}
    except Exception as e:
        logging.error(f"发送随机图片时发生错误: {str(e)}")
        await msg_util.send_text(
            target_id,
            f"获取图片失败: {str(e)}",
            is_private=is_private
        )
        return {}

async def handle_admin_command(user_id, command):
    """处理管理员命令"""
    if user_id != Config.ADMIN_ID:
        await msg_util.send_text(user_id, "权限不足", is_private=True)
        return {}
    
    try:
        if command == "服务状态":
            return await handle_service_status(user_id)
            
        elif command == "清理缓存":
            return await handle_cache_cleanup(user_id)
            
        elif command == "重载配置":
            return await handle_reload_config(user_id)
            
        else:
            await msg_util.send_text(
                user_id, 
                f"未知管理员命令: {command}", 
                is_private=True
            )
            return {}
    except Exception as e:
        logging.error(f"处理管理员命令时发生错误: {str(e)}")
        await msg_util.send_text(
            user_id,
            f"执行命令失败: {str(e)}",
            is_private=True
        )
        return {}

async def handle_private_message(user_id, message, message_array=None):
    """处理私聊消息"""
    try:
        # 处理授权命令
        if message.startswith("/auth"):
            logging.info(f"处理私聊授权命令: {message}")
            msg = await auth_manager.handle_auth_command(user_id, message)
            await msg_util.send_text(user_id, msg["message"], is_private=True)
            return {}
        
        if message == "粥表":
            await msg_util.send_image(
                user_id, 
                image_url=Config.MEDIA['schedule_image'],
                is_private=True
            )
            return {}
            
        elif message == "粥歌":
            return await handle_songs_images(user_id, is_private=True)
            
        elif message == "视频推荐":
            return await handle_video_request(user_id, is_private=True)
        
        elif message == "来张美图":
            return await handle_random_image(user_id, is_private=True)
        
        # 处理管理员命令
        elif message in ["服务状态", "清理缓存", "重载配置"]:
            return await handle_admin_command(user_id, message)
        
        # 处理普通聊天
        else:
            return await handle_private_chat(user_id, message, message_array)
    
    except Exception as e:
        logging.error(f"处理私聊消息时发生错误: {str(e)}")
        await msg_util.send_text(
            user_id,
            "处理消息时出现错误，请稍后再试",
            is_private=True
        )
        
        # 错误通知管理员
        await msg_util.send_text(
            Config.ADMIN_ID,
            f"私聊处理错误: 用户 {user_id}, 错误: {str(e)}",
            is_private=True
        )
        return {}

async def handle_service_status(user_id):
    """处理服务状态查询"""
    if user_id != Config.ADMIN_ID:
        return {}
    
    try:
        # 计算内存使用情况
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # 计算运行时间
        import datetime
        uptime = time.time() - process.create_time()
        uptime_str = str(datetime.timedelta(seconds=int(uptime)))
        
        # 计算API调用次数和用户数
        api_calls = len(user_chat_limiters) + len(user_video_limiters)
        unique_users = set(user_chat_limiters.keys()) | set(user_video_limiters.keys())
        
        status = (
            f"服务状态报告:\n"
            f"- 运行时间: {uptime_str}\n"
            f"- 内存使用: {memory_mb:.2f} MB\n"
            f"- API调用次数: {api_calls}\n"
            f"- 用户数: {len(unique_users)}\n"
            f"- 当前聊天限流器: {len(user_chat_limiters)}\n"
            f"- 当前视频限流器: {len(user_video_limiters)}"
        )
        
        await msg_util.send_text(user_id, status, is_private=True)
        return {}
    except Exception as e:
        logging.error(f"获取服务状态时出错: {str(e)}")
        await msg_util.send_text(
            user_id,
            f"获取服务状态失败: {str(e)}",
            is_private=True
        )
        return {}

async def handle_cache_cleanup(user_id):
    """清理系统缓存"""
    if user_id != Config.ADMIN_ID:
        return {}
    
    try:
        # 清理用户限流器
        cleared_chat = len(user_chat_limiters)
        cleared_video = len(user_video_limiters)
        
        user_chat_limiters.clear()
        user_video_limiters.clear()
                
        await msg_util.send_text(
            user_id,
            f"缓存清理完成:\n- 清除了 {cleared_chat} 个聊天限流器\n- 清除了 {cleared_video} 个视频限流器",
            is_private=True
        )
        logging.info(f"缓存清理完成: {cleared_chat} 个聊天限流器, {cleared_video} 个视频限流器")
        return {}
    except Exception as e:
        logging.error(f"清理缓存时出错: {str(e)}")
        await msg_util.send_text(
            user_id,
            f"清理缓存失败: {str(e)}",
            is_private=True
        )
        return {}

async def handle_reload_config(user_id):
    """重新加载配置"""
    if user_id != Config.ADMIN_ID:
        return {}
    
    try:
        # 重新加载配置
        Config.init()

        
        await msg_util.send_text(
            user_id,
            "配置重新加载完成",
            is_private=True
        )
        logging.info("配置重新加载完成")
        return {}
    except Exception as e:
        logging.error(f"重载配置时出错: {str(e)}")
        await msg_util.send_text(
            user_id,
            f"重载配置失败: {str(e)}",
            is_private=True
        )
        return {}

# 消息接收与处理
@app.post("/")
async def root(request: Request):
    """消息接收与处理"""
    try:
        data = await request.json()
        
        # 提取消息内容
        raw_message = data.get('raw_message', '')
        message_array = data.get('message', [])
        chat_user_id = data.get('user_id')
        group_id = data.get('group_id', "None")
        message_type = data.get('message_type')

        if not raw_message or not chat_user_id:
            logging.error("无效的请求数据")
            return {"status": "error", "message": "无效的请求数据"}

        # 处理私聊消息
        if message_type == "private":
            return await handle_private_message(chat_user_id, raw_message, message_array)

        # 处理群聊中的授权命令
        if raw_message.startswith("/auth"):
            logging.info(f"处理群聊授权命令: {raw_message}")
            msg = await auth_manager.handle_auth_command(chat_user_id, raw_message)
            # 在群里回复授权结果，带上@ 
            await msg_util.send_text(
                group_id,
                msg["message"],
                is_private=False,
                user_id=str(chat_user_id)
            )
            return {}
            
        # 处理群聊命令
        if raw_message == "粥表":
            await msg_util.send_image(
                group_id, 
                image_url=Config.MEDIA['schedule_image']
            )
            return {}
        
        elif raw_message == "早安":
            try:
                if greeting.get("07:00"):
                    await msg_util.send_message(
                        group_id,
                        {'type': 'record', 'data': {'file': greeting["07:00"]}}
                    )
                else:
                    await msg_util.send_text(
                        group_id,
                        "早安语音文件未配置",
                        is_private=False
                    )
                return {}
            except Exception as e:
                logging.error(f"发送早安语音时发生错误: {str(e)}")
                await msg_util.send_text(
                    group_id,
                    "发送早安语音失败，请稍后再试",
                    is_private=False
                )
                return {}
        
        elif raw_message == "晚安":
            try:
                if greeting.get("02:00"): 
                    await msg_util.send_message(
                        group_id,
                        {'type': 'record', 'data': {'file': greeting["02:00"]}}
                    )
                else:
                    await msg_util.send_text(
                        group_id,
                        "晚安语音文件未配置",
                        is_private=False
                    )
                return {}
            except Exception as e:
                logging.error(f"发送晚安语音时发生错误: {str(e)}")
                await msg_util.send_text(
                    group_id,
                    "发送晚安语音失败，请稍后再试",
                    is_private=False
                )
                return {}

        elif raw_message == "粥歌":
            return await handle_songs_images(group_id)
            
        elif raw_message == "视频推荐":
            return await handle_video_request(group_id)

        elif raw_message == "来张美图":
            return await handle_random_image(group_id, is_private=False)

        # 处理@机器人消息
        is_at_bot, actual_content = await extract_at_content(raw_message, message_array)
        if is_at_bot:
            # 传递完整message_array给handle_at_message
            return await handle_at_message(chat_user_id, int(group_id), actual_content, message_array)

    except Exception as e:
        logging.error(f"处理请求时发生错误: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return {"status": "error", "message": "服务器内部错误"}    

async def periodic_cleanup():
    """定期清理过期的限流器"""
    while True:
        try:
            current_time = time.time()
            inactive_threshold = current_time - 1800
            
            # 清理聊天限流器
            chat_inactive = []
            for user_id, limiter in user_chat_limiters.items():
                if limiter.last_time < inactive_threshold:
                    chat_inactive.append(user_id)
            
            for user_id in chat_inactive:
                user_chat_limiters.pop(user_id, None)
            
            # 清理视频限流器
            video_inactive = []
            for user_id, limiter in user_video_limiters.items():
                if limiter.last_time < inactive_threshold:
                    video_inactive.append(user_id)
            
            for user_id in video_inactive:
                user_video_limiters.pop(user_id, None)
                
            if chat_inactive or video_inactive:
                logging.info(f"自动清理: {len(chat_inactive)} 个聊天限流器, {len(video_inactive)} 个视频限流器")
            
        except Exception as e:
            logging.error(f"清理限流器时发生错误: {str(e)}")
            
        # 每10分钟执行一次
        await asyncio.sleep(600)

async def greetings():
    """定时消息发送"""
    while True:
        time_now = time.strftime("%H:%M", time.localtime())
        if time_now in greeting:
            await msg_util.send_message(
                Config.target_group_id, 
                {'type': 'record', 'data': {'file': greeting[time_now]}}
            )
            logging.info(f"定时发送问候语音到群 {Config.target_group_id}: {greeting[time_now]}")
            await asyncio.sleep(61)
        else:
            await asyncio.sleep(59)

def run_background_tasks():
    """在独立线程中运行后台任务"""
    try:
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logging.INFO("后台任务线程已创建")
        loop.run_until_complete(asyncio.gather(
            greetings(),
            periodic_cleanup()
        ))
    except Exception as e:
        logging.error(f"后台任务线程初始化失败: {str(e)}")

if __name__ == "__main__":
    background_thread = threading.Thread(target=run_background_tasks, daemon=True)
    background_thread.start()
    logging.info("后台任务线程已启动")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=True
    )