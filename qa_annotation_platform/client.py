"""
QA标注平台客户端（简化版）

供Oxygent Agent调用
"""
import asyncio
from typing import Any, Dict, List, Optional


class QAClient:
    """QA标注平台客户端（简化版）"""
    
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
        source_request_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        caller: str = "user",
        callee: str = "",
        data_type: Optional[str] = None,
        priority: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入数据（核心方法）
        
        Args:
            source_trace_id: 来自OxyRequest.current_trace_id（必填）
            source_request_id: 来自OxyRequest.request_id（必填）
            question: 问题/输入（必填）
            answer: 答案/输出（可选）
            source_group_id: 来自OxyRequest.group_id（可选，用于聚合）
            caller: 调用者（必填，如user/agent名称）
            callee: 被调用者（必填，如agent/tool/llm名称）
            data_type: 数据类型（可选，用于标注时区分来源）
            priority: 优先级（可选，默认0，P0=端到端）
            category: 分类（可选）
            tags: 标签列表（可选）
            extra: 额外数据（可选）
        
        Returns:
            API响应，包含data_id
        """
        payload = {
            "source_trace_id": source_trace_id,
            "source_request_id": source_request_id,
            "question": question,
            "answer": answer,
            "caller": caller,
            "callee": callee,
            "priority": priority
        }
        
        if source_group_id:
            payload["source_group_id"] = source_group_id
        if data_type:
            payload["data_type"] = data_type
        if category:
            payload["category"] = category
        if tags:
            payload["tags"] = tags
        if extra:
            payload["extra"] = extra
        
        return await self._request("POST", "/api/v1/deposit", payload)
    
    async def deposit_e2e(
        self,
        source_trace_id: str,
        source_request_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        callee: str = "",
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入端到端数据（P0优先级）
        
        快捷方法，等效于 priority=0
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            source_request_id=source_request_id,
            question=question,
            answer=answer,
            source_group_id=source_group_id,
            caller="user",
            callee=callee,
            data_type="e2e",
            priority=0,
            extra=extra
        )
    
    async def deposit_agent(
        self,
        source_trace_id: str,
        source_request_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        caller: str = "user",
        callee: str = "",
        priority: int = 1,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入Agent调用数据（P1）
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            source_request_id=source_request_id,
            question=question,
            answer=answer,
            source_group_id=source_group_id,
            caller=caller,
            callee=callee,
            data_type="agent",
            priority=priority,
            extra=extra
        )
    
    async def deposit_llm(
        self,
        source_trace_id: str,
        source_request_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        caller: str = "agent",
        callee: str = "llm",
        priority: int = 2,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入LLM调用数据（P2）
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            source_request_id=source_request_id,
            question=question,
            answer=answer,
            source_group_id=source_group_id,
            caller=caller,
            callee=callee,
            data_type="llm",
            priority=priority,
            extra=extra
        )
    
    async def deposit_tool(
        self,
        source_trace_id: str,
        source_request_id: str,
        question: str,
        answer: str = "",
        source_group_id: Optional[str] = None,
        caller: str = "agent",
        callee: str = "",
        priority: int = 3,
        extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        注入Tool调用数据（P3）
        """
        return await self.deposit(
            source_trace_id=source_trace_id,
            source_request_id=source_request_id,
            question=question,
            answer=answer,
            source_group_id=source_group_id,
            caller=caller,
            callee=callee,
            data_type="tool",
            priority=priority,
            extra=extra
        )
    
    async def batch_deposit(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量注入数据"""
        return await self._request("POST", "/api/v1/deposit/batch", {"items": items})
    
    async def get_data_list(
        self,
        caller: Optional[str] = None,
        callee: Optional[str] = None,
        data_type: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        group_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        show_p0_only: bool = False,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取数据列表"""
        params = {
            "page": page,
            "page_size": page_size
        }
        if caller:
            params["caller"] = caller
        if callee:
            params["callee"] = callee
        if data_type:
            params["data_type"] = data_type
        if status:
            params["status"] = status
        if priority is not None:
            params["priority"] = priority
        if group_id:
            params["group_id"] = group_id
        if trace_id:
            params["trace_id"] = trace_id
        if show_p0_only:
            params["show_p0_only"] = True
        
        query = "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return await self._request("GET", f"/api/v1/data{query}")
    
    async def get_data_by_trace(self, trace_id: str) -> Dict[str, Any]:
        """根据trace_id获取所有关联数据"""
        return await self._request("GET", f"/api/v1/data/trace/{trace_id}")
    
    async def get_data_by_group(self, group_id: str, limit: int = 100) -> Dict[str, Any]:
        """根据group_id获取所有关联数据"""
        return await self._request("GET", f"/api/v1/data/group/{group_id}?limit={limit}")
    
    async def get_groups_summary(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取分组汇总"""
        return await self._request("GET", f"/api/v1/data/groups/summary?page={page}&page_size={page_size}")
    
    async def get_data(self, data_id: str) -> Dict[str, Any]:
        """获取数据详情"""
        return await self._request("GET", f"/api/v1/data/{data_id}")
    
    async def annotate(
        self,
        data_id: str,
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
        
        return await self._request("PUT", f"/api/v1/data/{data_id}/annotate", payload)
    
    async def approve(self, data_id: str) -> Dict[str, Any]:
        """审核通过"""
        return await self._request("POST", f"/api/v1/data/{data_id}/approve", {})
    
    async def reject(self, data_id: str) -> Dict[str, Any]:
        """审核拒绝"""
        return await self._request("POST", f"/api/v1/data/{data_id}/reject", {})
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return await self._request("GET", "/api/v1/stats")
    
    async def get_pending_p0(self) -> Dict[str, Any]:
        """获取待标注的P0数据"""
        return await self._request("GET", "/api/v1/stats/pending-p0")


class QADepositor:
    """同步版QA注入器（兼容非异步代码）"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.client = QAClient(base_url)
    
    def deposit(self, **kwargs) -> Dict[str, Any]:
        """同步注入数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit(**kwargs))
            return future.result()
    
    def deposit_e2e(self, **kwargs) -> Dict[str, Any]:
        """同步注入端到端数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_e2e(**kwargs))
            return future.result()
    
    def deposit_agent(self, **kwargs) -> Dict[str, Any]:
        """同步注入Agent数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_agent(**kwargs))
            return future.result()
    
    def deposit_llm(self, **kwargs) -> Dict[str, Any]:
        """同步注入LLM数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_llm(**kwargs))
            return future.result()
    
    def deposit_tool(self, **kwargs) -> Dict[str, Any]:
        """同步注入Tool数据"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_tool(**kwargs))
            return future.result()


def create_qa_client(base_url: str = "http://localhost:8001") -> QAClient:
    """创建QA客户端"""
    return QAClient(base_url)


def create_qa_depositor(base_url: str = "http://localhost:8001") -> QADepositor:
    """创建同步QA注入器"""
    return QADepositor(base_url)
