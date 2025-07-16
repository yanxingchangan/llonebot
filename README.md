# QQ群聊机器人系统

一个基于FastAPI的多功能QQ群聊机器人，支持AI聊天、图片管理、视频推荐、定时消息等功能。

## 项目架构

本项目基于 [llonebot](https://github.com/LLOneBot/LLOneBot) 构建，采用以下架构：

```
QQ客户端 → LLOneBot → HTTP POST  → 本项目 → API响应 → LLOneBot → QQ客户端
```

- **LLOneBot**: 作为QQ机器人框架，负责接收QQ消息并转发给本项目
- **本项目**: 处理业务逻辑，提供AI聊天、图片管理等功能
- **通信方式**: LLOneBot上报JSON格式的消息，本项目通过API接口响应

## 功能特性

### AI聊天功能
- 基于DeepSeek API的智能对话
- 支持@机器人触发对话
- 用户会话管理和超时清理
- 自定义用户预设配置

### 图片管理
- 图片数据库存储（Base64编码）
- 感知哈希算法防重复图片
- 相似图片检测和查找
- 随机图片发送功能

### 视频推荐
- 随机视频推荐系统
- B站视频信息获取
- 视频请求限流控制

### 权限管理
- 管理员命令系统
- 用户授权管理
- 一次性Token生成
- 多级权限控制

### 限流保护
- 令牌桶算法实现
- 全局和用户级限流
- 防止API滥用
- 可配置限流参数

### 定时功能
- 定时问候消息
- 定期清理过期数据
- 可配置时间点

## 环境要求

- Python 3.8+
- SQLite3
- 依赖包见下方安装说明

## 安装部署

### 前置要求
1. 安装并配置 [LLOneBot](https://github.com/LLOneBot/LLOneBot)
2. 确保LLOneBot配置正确，能够向本项目上报消息

### 1. 克隆项目
```bash
git clone git@github.com:yanxingchangan/llonebot.git
cd qq-bot-system
```

### 2. 安装依赖
```bash
pip install fastapi uvicorn httpx requests pandas pillow numpy sqlite3
```

### 3. 配置文件
编辑 `config.py` 文件，填入必要的配置信息：

```python
class Config:
    # API配置
    API_KEY = "your_deepseek_api_key"  # DeepSeek API密钥
    
    # 系统配置
    ADMIN_ID = "your_admin_qq_id"      # 机器人最高管理员QQ号
    target_group_id = "target_group"    # 目标群组ID
    ADMIN_SERVER = "http://localhost:3000/send_msg"           # 私聊API地址
    LOCAL_SERVER = "http://localhost:3000/send_group_msg"     # 群聊API地址
    BILIBILI_COOKIE = "SESSDATA=xxx; bili_jct=xxx;"          # B站Cookie
```

### 4. 配置LLOneBot
确保LLOneBot配置文件中包含以下设置：
```json
{
  "http": {
    "enable": true,
    "host": "0.0.0.0",
    "port": 8080,
    "secret": "",
    "enableHeart": true,
    "enablePost": true,
    "postUrls": ["http://0.0.0.0:8080"]
  }
}
```

### 5. 启动应用
```bash
python main.py
```

应用将在 `http://0.0.0.0:8080` 启动，接收来自LLOneBot的消息上报。



## 使用说明

### 基本功能

#### 1. AI聊天
- 在群聊中@机器人即可开始对话
- 支持图片识别和分析
- 自动会话管理

#### 2. 管理员命令
发送以下命令给机器人（仅管理员）：

- `/auth add <user_id>` - 添加授权用户
- `/auth remove <user_id>` - 移除授权用户
- `/auth list` - 查看授权用户列表
- `/auth token <user_id>` - 生成一次性授权token
- `/auth clear` - 清除所有用户授权
- `/auth command` - 显示命令列表

#### 3. 其他功能
- `获取视频` - 随机推荐视频
- `随机图片` - 发送随机图片
- `粥歌图片` - 发送特定图片

### API接口

#### POST /
接收来自LLOneBot的消息上报接口

请求格式（LLOneBot标准格式）：
```json
{
    "post_type": "message",
    "message_type": "group",
    "group_id": 123456,
    "user_id": 789012,
    "message": "消息内容",
    "raw_message": "原始消息",
    "message_array": [...]
}
```

响应处理：
- 本项目接收到消息后，会根据消息类型和内容执行相应的业务逻辑
- 通过配置的API地址（`LOCAL_SERVER`、`ADMIN_SERVER`）向LLOneBot发送响应
- LLOneBot接收到响应后转发给QQ用户

## 核心模块说明

### TokenBucket 令牌桶
实现了令牌桶限流算法，防止API请求过于频繁：
- `capacity`: 桶容量
- `fill_rate`: 令牌填充速率
- `consume()`: 消耗令牌

### ImageDatabaseManager 图片管理
- 使用感知哈希算法检测相似图片
- SQLite数据库存储Base64编码图片
- 支持相似度阈值配置

### AuthManager 权限管理
- 用户授权和权限检查
- 一次性Token机制
- 管理员命令处理

### ChatManager 聊天管理
- 会话状态管理
- API请求处理
- 响应格式化

## 配置说明

### 限流配置
```python
# 全局限流器
chat_limiter = TokenBucket(5, 5)    # 每秒5个聊天请求
video_limiter = TokenBucket(10, 3)  # 每秒3个视频请求

# 用户级限流
user_limiters[user_id] = TokenBucket(1, 1)  # 每用户每秒1个请求
```

### 定时消息
```python
greeting_times_1 = {
    "07:00": r"E:/project/get up.wav",      # 早上问候
    "02:00": r"E:/project/good night.wav",  # 晚安问候
}
```

## 日志记录

系统会自动记录运行日志到 `group_chat_system.log` 文件，包括：
- 消息处理记录
- 错误信息
- API请求状态
- 用户操作日志

## 注意事项

1. **API密钥安全**：请妥善保管DeepSeek API密钥
2. **数据库备份**：定期备份 `image_data.db` 图片数据库
3. **内存管理**：长时间运行需要注意内存使用情况
4. **限流设置**：根据实际需求调整限流参数
5. **权限控制**：谨慎授权用户权限，避免滥用

## 故障排除

### 常见问题

1. **API请求失败**
   - 检查网络连接
   - 验证API密钥
   - 查看请求限制

2. **数据库错误**
   - 检查SQLite文件权限
   - 验证数据库完整性
   - 查看磁盘空间

3. **消息发送失败**
   - 检查LLOneBot状态和配置
   - 验证API地址配置（LOCAL_SERVER、ADMIN_SERVER）
   - 检查群组权限和QQ客户端状态
   - 查看网络连接

4. **LLOneBot连接问题**
   - 确认LLOneBot正常运行
   - 检查LLOneBot配置文件中的HTTP设置
   - 验证端口8080是否被正确监听
   - 查看LLOneBot日志

### 日志查看
```bash
tail -f group_chat_system.log
```

## 许可证

本项目采用GPL-2.0许可证，详见LICENSE文件。

## 更新日志

### v1.0.0
- 初始版本发布
- 基础聊天功能
- 图片管理系统
- 权限管理
- 限流保护

---

如有问题或建议，请通过Issue提出


## 工作流程

1. **消息接收**: LLOneBot接收QQ消息并转换为JSON格式
2. **消息上报**: LLOneBot通过HTTP POST向本项目的`/`接口上报消息
3. **消息处理**: 本项目解析消息内容，执行相应的业务逻辑
4. **API调用**:  本项目通过配置的API地址向LLOneBot发送响应
5. **消息发送**: LLOneBot将响应转发给相应的QQ用户或群组
```
