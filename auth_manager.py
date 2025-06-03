import time
import secrets
from typing import Dict, Set, Tuple, Optional, ClassVar
from dataclasses import dataclass, field

@dataclass
class AuthManager:
    """授权管理器类"""
    admin_id: int
    authorized_users: Set[int] = field(default_factory=set)
    one_time_tokens: Dict[str, Tuple[float, int]] = field(default_factory=dict)
    
    # 类常量：bot管理员命令列表
    ADMIN_COMMANDS: ClassVar[Dict[str, str]] = {
        "/auth add <user_id>": "添加授权用户",
        "/auth remove <user_id>": "移除授权用户", 
        "/auth list": "查看授权用户列表",
        "/auth token <user_id>": "生成一次性授权token",
        "/auth clear": "移除所有用户授权（管理员除外）",
        "/auth command": "显示管理员命令"
    }

    def __post_init__(self):
        self.authorized_users.add(self.admin_id)

    def is_authorized(self, user_id: int) -> bool:
        return user_id in self.authorized_users

    def is_admin(self, user_id: int) -> bool:
        return user_id == self.admin_id

    async def generate_one_time_token(self, target_id: int) -> str:
        self.cleanup_expired_tokens()
        token = secrets.token_urlsafe(16)
        expiry_time = time.time() + 600
        self.one_time_tokens[token] = (expiry_time, target_id)
        return token

    async def handle_auth_command(self, user_id: int, message: str) -> Dict[str, str]:
        """处理授权命令"""
        parts = message.strip().split()
        
        # 基本命令格式验证
        if not parts or parts[0] != "/auth":
            return {"message": "无效的命令格式"}
        
        # 非管理员只能使用token
        if not self.is_admin(user_id):
            if len(parts) == 2 and parts[0] == "/auth":
                token = parts[1]
                valid, target_id, msg = self.validate_token(token)
                if valid:
                    msg = self.add_user(target_id)
                    return {"message": msg}
                return {"message": msg}
            return {"message": "权限不足"}
        
        # 管理员命令处理
        if len(parts) == 2:
            command = parts[1]
            if command == "list":
                return {"message": self.get_user_list()}
            elif command == "command":
                return {"message": self.get_command_list()}
            elif command == "clear":
                return self.clear_all_authorizations()
                
        if len(parts) == 3:
            action, target = parts[1:]
            try:
                target_id = int(target)
                
                if action == "add":
                    return {"message": self.add_user(target_id)}
                
                elif action == "remove":
                    return {"message": self.remove_user(target_id)}
                
                elif action == "token":
                    token = await self.generate_one_time_token(target_id)
                    return {"message": f"已生成一次性Token: {token}"}
                    
            except ValueError:
                return {"message": "用户ID必须为数字"}
        
        return {"message": "无效的命令格式"}

    def validate_token(self, token: str) -> Tuple[bool, Optional[int], str]:
        if token not in self.one_time_tokens:
            return False, None, "无效的Token"
            
        expiry_time, target_id = self.one_time_tokens[token]
        if time.time() > expiry_time:
            del self.one_time_tokens[token]
            return False, None, "Token已过期"
            
        del self.one_time_tokens[token]
        return True, target_id, "Token验证成功"

    def add_user(self, target_id: int) -> str:
        if target_id in self.authorized_users:
            return f"用户 {target_id} 已在授权列表中"
        self.authorized_users.add(target_id)
        return f"已添加用户 {target_id} 到授权列表"

    def remove_user(self, target_id: int) -> str:
        if target_id == self.admin_id:
            return "不能移除管理员权限"
        if target_id not in self.authorized_users:
            return f"用户 {target_id} 不在授权列表中"
        self.authorized_users.remove(target_id)
        return f"已从授权列表中移除用户 {target_id}"

    def get_user_list(self) -> str:
        if not self.authorized_users:
            return "当前授权用户列表为空"
        return f"当前授权用户列表：{sorted(self.authorized_users)}"

    def get_command_list(self) -> str:
        return "\n".join([f"{cmd}: {desc}" for cmd, desc in self.ADMIN_COMMANDS.items()])

    def clear_all_authorizations(self):
        """移除所有非管理员用户的授权"""
        try:
            # 获取当前授权用户数量（不包括管理员）
            before_count = len(self.authorized_users - {self.admin_id})
            
            # 保留管理员，清空其他所有授权
            new_authorized_users = {self.admin_id} if self.admin_id in self.authorized_users else set()
            self.authorized_users = new_authorized_users
            
            return {"message": f"已清除所有用户授权（管理员除外），共移除 {before_count} 个用户"}
        except Exception as e:
            return {"message": f"清除授权失败: {str(e)}"}

    def cleanup_expired_tokens(self):
        current_time = time.time()
        expired_tokens = [
            token for token, (expiry, _) in self.one_time_tokens.items()
            if expiry < current_time
        ]
        for token in expired_tokens:
            del self.one_time_tokens[token]