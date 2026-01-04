"""
QA Annotation Platform Client (Simplified)

For Oxygent Agent to call
"""
import asyncio
from typing import Any, Dict, List, Optional


class QAClient:
    """QA Annotation Platform Client (Simplified)"""
    
    def __init__(self, base_url: str = "http://localhost:8001", timeout: int = 30):
        """
        Initialize client
        
        Args:
            base_url: QA Annotation Platform API address
            timeout: Request timeout (seconds)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Send HTTP request"""
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
        Deposit data (Core method)
        
        Args:
            source_trace_id: From OxyRequest.current_trace_id (required)
            source_request_id: From OxyRequest.request_id (required)
            question: Question/Input (required)
            answer: Answer/Output (optional)
            source_group_id: From OxyRequest.group_id (optional, for aggregation)
            caller: Caller (required, e.g., user/agent name)
            callee: Callee (required, e.g., agent/tool/llm name)
            data_type: Data type (optional, used to distinguish source during annotation)
            priority: Priority (optional, default 0, P0=End-to-End)
            category: Category (optional)
            tags: Tags list (optional)
            extra: Extra data (optional)
        
        Returns:
            API response, containing data_id
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
        Deposit End-to-End data (P0 priority)
        
        Convenience method, equivalent to priority=0
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
        Deposit Agent call data (P1)
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
        Deposit LLM call data (P2)
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
        Deposit Tool call data (P3)
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
        """Batch deposit data"""
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
        """Get data list"""
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
        """Get all related data by trace_id"""
        return await self._request("GET", f"/api/v1/data/trace/{trace_id}")
    
    async def get_data_by_group(self, group_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get all related data by group_id"""
        return await self._request("GET", f"/api/v1/data/group/{group_id}?limit={limit}")
    
    async def get_groups_summary(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """Get grouped summary"""
        return await self._request("GET", f"/api/v1/data/groups/summary?page={page}&page_size={page_size}")
    
    async def get_data(self, data_id: str) -> Dict[str, Any]:
        """Get data details"""
        return await self._request("GET", f"/api/v1/data/{data_id}")
    
    async def annotate(
        self,
        data_id: str,
        annotation: Dict[str, Any],
        scores: Optional[Dict[str, float]] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update annotation result"""
        payload = {" ntation": annotation}
        if scores:
            payload["scores"] = scores
        if status:
            payload["status"] = status
        
        return await self._request("PUT", f"/api/v1/data/{data_id}/annotate", payload)
    
    async def approve(self, data_id: str) -> Dict[str, Any]:
        """Approve review"""
        return await self._request("POST", f"/api/v1/data/{data_id}/approve", {})
    
    async def reject(self, data_id: str) -> Dict[str, Any]:
        """Reject review"""
        return await self._request("POST", f"/api/v1/data/{data_id}/reject", {})
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return await self._request("GET", "/api/v1/stats")
    
    async def get_pending_p0(self) -> Dict[str, Any]:
        """Get pending P0 data"""
        return await self._request("GET", "/api/v1/stats/pending-p0")


class QADepositor:
    """Synchronous QA Depositor (compatible with non-async code)"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.client = QAClient(base_url)
    
    def deposit(self, **kwargs) -> Dict[str, Any]:
        """Synchronous deposit data"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit(**kwargs))
            return future.result()
    
    def deposit_e2e(self, **kwargs) -> Dict[str, Any]:
        """Synchronous deposit End-to-End data"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_e2e(**kwargs))
            return future.result()
    
    def deposit_agent(self, **kwargs) -> Dict[str, Any]:
        """Synchronous deposit Agent data"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_agent(**kwargs))
            return future.result()
    
    def deposit_llm(self, **kwargs) -> Dict[str, Any]:
        """Synchronous deposit LLM data"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_llm(**kwargs))
            return future.result()
    
    def deposit_tool(self, **kwargs) -> Dict[str, Any]:
        """Synchronous deposit Tool data"""
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self.client.deposit_tool(**kwargs))
            return future.result()


def create_qa_client(base_url: str = "http://localhost:8001") -> QAClient:
    """Create QA client"""
    return QAClient(base_url)


def create_qa_depositor(base_url: str = "http://localhost:8001") -> QADepositor:
    """Create synchronous QA depositor"""
    return QADepositor(base_url)
