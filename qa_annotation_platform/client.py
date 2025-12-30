"""
QA标注平台客户端

供Oxygent Agent调用
"""
import asyncio
from typing import Any, Dict, List, Optional


class QAClient:
    """QA标注平台客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8001", timeout: int = 30):
        """
        初始化客户端
        
        Args:
            base_url: QA标注平台API地址
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """发起HTTP请求"""
        import aiohttp
        
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers, timeout=self.timeout) as resp:
                    return await resp.json()
            else:
                async with session.request(method, url, json=data, headers=headers, timeout=self.timeout) as resp:
                    return await resp.json()
    
    async def deposit(
        self,
        source_trace_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
        parent_qa_id: Optional[str] = None,
        is_root: bool = False,
        source_type: Optional[str] = None,
        priority: Optional[int] = None,
        caller: Optional[str] = None,
        callee: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入QA数据
        
        Args:
            source_trace_id: 来自OxyRequest.current_trace_id（必填）
            question: 问题/输入（必填）
            answer: 答案/输出（可选）
            source_group_id: 来自OxyRequest.group_id（可选）
            source_node_id: 节点ID（可选）
            parent_qa_id: 父QA ID（可选，用于子节点串联）
            is_root: 是否为根节点（可选，默认False）
            source_type: 来源类型（可选，自动推断）
            priority: 优先级0-4（可选，自动推断）
            caller: 调用者（可选）
            callee: 被调用者（可选）
            category: 分类（可选）
            tags: 标签列表（可选）
            extra: 额外数据（可选）
        
        Returns:
            API响应
        """
        payload = {
            "source_trace_id": source_trace_id,
            "question": question,
            "answer": answer,
            "is_root": is_root
        }
        
        if source_group_id:
            payload["source_group_id"] = source_group_id
        if source_node_id:
            payload["source_node_id"] = source_node_id
        if parent_qa_id:
            payload["parent_qa_id"] = parent_qa_id
        if source_type:
            payload["source_type"] = source_type
        if priority is not None:
            payload["priority"] = priority
        if caller:
            payload["caller"] = caller
        if callee:
            payload["callee"] = callee
        if category:
            payload["category"] = category
        if tags:
            payload["tags"] = tags
        if extra:
            payload["extra"] = extra
        
        return await self._request("POST", "/api/v1/deposit", payload)
    
    async def deposit_root(
        self,
        source_trace_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        caller: Optional[str] = None,
        callee: Optional[str] = None,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入根节点（端到端QA）
        
        快捷方法，等效于 is_root=True
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            question=question,
            answer=answer,
            source_group_id=source_group_id,
            is_root=True,
            caller=caller,
            callee=callee,
            extra=extra
        )
    
    async def deposit_child(
        self,
        parent_qa_id: str,
        source_trace_id: str,
        question: str,
        answer: str = "",
        source_type: Optional[str] = None,
        priority: Optional[int] = None,
        caller: Optional[str] = None,
        callee: Optional[str] = None,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入子节点（自动串联到父节点）
        
        Args:
            parent_qa_id: 父QA ID
            source_trace_id: trace_id（应与父节点相同）
            question: 输入
            answer: 输出
            source_type: 节点类型
            priority: 优先级
            caller: 调用者
            callee: 被调用者
            extra: 额外数据
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            question=question,
            answer=answer,
            parent_qa_id=parent_qa_id,
            source_type=source_type,
            priority=priority,
            caller=caller,
            callee=callee,
            extra=extra
        )
    
    async def batch_deposit(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量注入QA数据"""
        return await self._request("POST", "/api/v1/deposit/batch", {"items": items})
    
    async def get_tasks(
        self,
        qa_type: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取任务列表"""
        params = {"page": page, "page_size": page_size}
        if qa_type:
            params["qa_type"] = qa_type
        if status:
            params["status"] = status
        if priority is not None:
            params["priority"] = priority
        
        query = "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return await self._request("GET", f"/api/v1/tasks{query}")
    
    async def annotate(
        self,
        qa_id: str,
        annotation: Dict[str, Any],
        scores: Optional[Dict[str, float]] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """更新标注结果"""
        payload = {"annotation": annotation}
        if scores:
            payload["scores"] = scores
        if status:
            payload["status"] = status
        
        return await self._request("PUT", f"/api/v1/tasks/{qa_id}/annotate", payload)
    
    async def approve(self, qa_id: str) -> Dict[str, Any]:
        """审核通过"""
        return await self._request("POST", f"/api/v1/tasks/{qa_id}/approve", {})
    
    async def reject(self, qa_id: str) -> Dict[str, Any]:
        """审核拒绝"""
        return await self._request("POST", f"/api/v1/tasks/{qa_id}/reject", {})


class QADepositor:
    """同步版QA注入器（兼容非异步代码）"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.client = QAClient(base_url)
    
    def deposit(self, **kwargs) -> Dict[str, Any]:
        """同步注入QA数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit(**kwargs))
            return future.result()
    
    def deposit_root(self, **kwargs) -> Dict[str, Any]:
        """同步注入根节点"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_root(**kwargs))
            return future.result()


def create_qa_client(base_url: str = "http://localhost:8001") -> QAClient:
    """创建QA客户端"""
    return QAClient(base_url)


def create_qa_depositor(base_url: str = "http://localhost:8001") -> QADepositor:
    """创建同步QA注入器"""
    return QADepositor(base_url)

