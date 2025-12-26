#!/usr/bin/env python3
"""
简化的多Agent系统QA数据提取工具

基于OxyGent框架的ES存储数据分析，提供端到端和Agent间QA数据提取
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class QAItem:
    """QA项目数据结构"""
    source: str  # "end_to_end" 或 "agent_to_agent"
    query: str
    answer: str
    session_name: str
    trace_id: str
    node_id: Optional[str] = None
    call_stack: Optional[List[str]] = None
    timestamp: Optional[str] = None
    additional_info: Optional[Dict] = None


class SimpleMultiAgentQAExtractor:
    """简化的多Agent系统QA数据提取器"""
    
    def __init__(self, cache_dir: str = "cache_dir/local_es_data"):
        self.cache_dir = cache_dir
        self.history_file = os.path.join(cache_dir, "app_history.json")
        self.node_file = os.path.join(cache_dir, "app_node.json")
        self.trace_file = os.path.join(cache_dir, "app_trace.json")
    
    def load_data(self) -> Tuple[Dict, Dict, Dict]:
        """加载所有ES数据文件"""
        print("正在加载ES数据文件...")
        
        # 加载历史数据
        with open(self.history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        # 加载节点数据
        with open(self.node_file, 'r', encoding='utf-8') as f:
            node_data = json.load(f)
        
        # 加载跟踪数据
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_data = json.load(f)
        
        print(f"已加载数据：")
        print(f"  - 历史记录: {len(history_data)} 条")
        print(f"  - 节点记录: {len(node_data)} 条")
        print(f"  - 跟踪记录: {len(trace_data)} 条")
        
        return history_data, node_data, trace_data
    
    def analyze_session_patterns(self, history_data: Dict) -> Dict[str, List[str]]:
        """分析session_name的类型模式"""
        print("正在分析Session模式...")
        
        patterns = {
            "end_to_end": [],  # user__agent 格式
            "agent_to_agent": [],  # agent__agent 格式
            "other": []
        }
        
        session_examples = {
            "end_to_end": set(),
            "agent_to_agent": set(),
            "other": set()
        }
        
        for history_id, record in history_data.items():
            session_name = record.get("session_name", "")
            
            if session_name.startswith("user__"):
                patterns["end_to_end"].append(session_name)
                session_examples["end_to_end"].add(session_name)
            elif "__" in session_name and not session_name.startswith("user__"):
                patterns["agent_to_agent"].append(session_name)
                session_examples["agent_to_agent"].add(session_name)
            else:
                patterns["other"].append(session_name)
                session_examples["other"].add(session_name)
        
        # 转换为去重列表
        for key in patterns:
            patterns[key] = list(set(patterns[key]))
        
        # 打印分析结果
        print(f"Session模式分析结果：")
        print(f"  - 端到端Session: {len(session_examples['end_to_end'])} 种唯一类型")
        print(f"  - Agent间Session: {len(session_examples['agent_to_agent'])} 种唯一类型")
        print(f"  - 其他Session: {len(session_examples['other'])} 种唯一类型")
        
        if session_examples["end_to_end"]:
            print(f"  端到端示例: {list(session_examples['end_to_end'])[:3]}")
        if session_examples["agent_to_agent"]:
            print(f"  Agent间示例: {list(session_examples['agent_to_agent'])[:3]}")
        
        return patterns
    
    def extract_end_to_end_qa(self, history_data: Dict) -> List[QAItem]:
        """提取端到端的用户-主Agent对话"""
        print("正在提取端到端对话...")
        
        qa_items = []
        
        for history_id, record in history_data.items():
            session_name = record.get("session_name", "")
            
            # 只处理user__agent格式的session
            if not session_name.startswith("user__"):
                continue
            
            # 解析memory字段
            try:
                memory_data = json.loads(record.get("memory", "{}"))
                query = memory_data.get("query", "")
                answer = memory_data.get("answer", "")
                
                if query and answer:
                    qa_item = QAItem(
                        source="end_to_end",
                        query=query,
                        answer=answer,
                        session_name=session_name,
                        trace_id=record.get("trace_id", ""),
                        timestamp=record.get("create_time", ""),
                        additional_info={
                            "history_id": history_id,
                            "raw_memory": memory_data
                        }
                    )
                    qa_items.append(qa_item)
            except (json.JSONDecodeError, TypeError):
                print(f"Warning: 无法解析memory数据 for {history_id}")
                continue
        
        print(f"提取到 {len(qa_items)} 条端到端对话")
        return qa_items
    
    def extract_agent_to_agent_qa(self, history_data: Dict) -> List[QAItem]:
        """提取Agent之间的对话"""
        print("正在提取Agent间对话...")
        
        qa_items = []
        
        for history_id, record in history_data.items():
            session_name = record.get("session_name", "")
            
            # 处理agent__agent格式的session
            if "__" in session_name and not session_name.startswith("user__"):
                try:
                    memory_data = json.loads(record.get("memory", "{}"))
                    query = memory_data.get("query", "")
                    answer = memory_data.get("answer", "")
                    
                    if query and answer:
                        # 从session_name中提取caller和callee
                        parts = session_name.split("__")
                        if len(parts) >= 2:
                            caller_agent = parts[0]
                            callee_agent = parts[1]
                            
                            qa_item = QAItem(
                                source="agent_to_agent",
                                query=query,
                                answer=answer,
                                session_name=session_name,
                                trace_id=record.get("trace_id", ""),
                                timestamp=record.get("create_time", ""),
                                additional_info={
                                    "history_id": history_id,
                                    "caller_agent": caller_agent,
                                    "callee_agent": callee_agent,
                                    "raw_memory": memory_data
                                }
                            )
                            qa_items.append(qa_item)
                except (json.JSONDecodeError, TypeError):
                    print(f"Warning: 无法解析memory数据 for {history_id}")
                    continue
        
        print(f"提取到 {len(qa_items)} 条Agent间对话")
        return qa_items
    
    def extract_node_level_qa(self, node_data: Dict) -> List[QAItem]:
        """从节点数据中提取详细的agent交互"""
        print("正在从节点数据中提取详细交互...")
        
        qa_items = []
        
        for node_id, node_record in node_data.items():
            # 只处理agent和tool类型的节点
            node_type = node_record.get("node_type", "")
            if node_type not in ["agent", "tool"]:
                continue
            
            caller = node_record.get("caller", "")
            callee = node_record.get("callee", "")
            
            # 从input中提取query
            try:
                input_data = json.loads(node_record.get("input", "{}"))
                query = input_data.get("query", "")
                
                output = node_record.get("output", "")
                
                if query and output:
                    qa_item = QAItem(
                        source="node_level_interaction",
                        query=query,
                        answer=output,
                        session_name=f"{caller}__{callee}",
                        trace_id=node_record.get("trace_id", ""),
                        node_id=node_id,
                        call_stack=node_record.get("call_stack", []),
                        timestamp=node_record.get("create_time", ""),
                        additional_info={
                            "node_type": node_type,
                            "caller": caller,
                            "callee": callee,
                            "input_data": input_data,
                            "raw_output": output
                        }
                    )
                    qa_items.append(qa_item)
            except (json.JSONDecodeError, TypeError):
                continue
        
        print(f"提取到 {len(qa_items)} 条详细节点交互")
        return qa_items
    
    def export_qa_data(self, qa_items: List[QAItem], output_file: str):
        """导出QA数据为JSON格式"""
        print(f"正在导出QA数据到 {output_file}...")
        
        export_data = []
        for qa_item in qa_items:
            export_data.append({
                "source": qa_item.source,
                "query": qa_item.query,
                "answer": qa_item.answer,
                "session_name": qa_item.session_name,
                "trace_id": qa_item.trace_id,
                "node_id": qa_item.node_id,
                "call_stack": qa_item.call_stack,
                "timestamp": qa_item.timestamp,
                "additional_info": qa_item.additional_info
            })
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"已导出 {len(export_data)} 条QA数据")
    
    def generate_analysis_report(self, qa_items: List[QAItem], session_patterns: Dict) -> str:
        """生成详细的分析报告"""
        report = []
        report.append("# OxyGent多Agent系统QA数据分析报告\n")
        
        # 数据概览
        report.append("## 数据概览\n")
        report.append(f"- 总QA对数: {len(qa_items)}")
        
        source_counts = {}
        session_names = set()
        trace_ids = set()
        
        for item in qa_items:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
            session_names.add(item.session_name)
            trace_ids.add(item.trace_id)
        
        for source, count in source_counts.items():
            report.append(f"- {source}: {count} 对")
        
        report.append(f"- 涉及Session数: {len(session_names)}")
        report.append(f"- 涉及Trace数: {len(trace_ids)}")
        report.append("")
        
        # Session模式分析
        report.append("## Session模式分析\n")
        report.append(f"- 端到端Session类型: {len(session_patterns['end_to_end'])} 种")
        report.append(f"- Agent间Session类型: {len(session_patterns['agent_to_agent'])} 种")
        report.append(f"- 其他Session类型: {len(session_patterns['other'])} 种")
        report.append("")
        
        # 端到端对话分析
        end_to_end_items = [item for item in qa_items if item.source == "end_to_end"]
        if end_to_end_items:
            report.append("## 端到端对话详细分析\n")
            report.append(f"共 {len(end_to_end_items)} 条端到端对话:")
            report.append("")
            
            # 按session分组
            session_groups = {}
            for item in end_to_end_items:
                session = item.session_name
                if session not in session_groups:
                    session_groups[session] = []
                session_groups[session].append(item)
            
            for session, items in list(session_groups.items())[:5]:  # 只显示前5个
                report.append(f"### {session} ({len(items)} 条对话)")
                for i, item in enumerate(items[:2]):  # 每个session显示2个样例
                    report.append(f"**样例 {i+1}:**")
                    report.append(f"- Query: {item.query[:100]}{'...' if len(item.query) > 100 else ''}")
                    report.append(f"- Answer: {item.answer[:100]}{'...' if len(item.answer) > 100 else ''}")
                    report.append(f"- 时间: {item.timestamp}")
                    report.append("")
        
        # Agent间对话分析
        agent_items = [item for item in qa_items if "agent_to_agent" in item.source]
        if agent_items:
            report.append("## Agent间对话详细分析\n")
            report.append(f"共 {len(agent_items)} 条Agent间对话:")
            report.append("")
            
            # 按调用关系分组
            caller_callee_pairs = {}
            for item in agent_items:
                pair = item.session_name
                if pair not in caller_callee_pairs:
                    caller_callee_pairs[pair] = []
                caller_callee_pairs[pair].append(item)
            
            for pair, items in list(caller_callee_pairs.items())[:5]:  # 只显示前5个
                report.append(f"### {pair} ({len(items)} 次交互)")
                for i, item in enumerate(items[:2]):  # 每个pair显示2个样例
                    report.append(f"**样例 {i+1}:**")
                    report.append(f"- Query: {item.query[:100]}{'...' if len(item.query) > 100 else ''}")
                    report.append(f"- Answer: {item.answer[:100]}{'...' if len(item.answer) > 100 else ''}")
                    report.append(f"- Trace: {item.trace_id}")
                    report.append("")
        
        return "\n".join(report)
    
    def run_full_extraction(self, output_file: str = "extracted_qa_data.json", 
                          report_file: str = "qa_analysis_report.md"):
        """运行完整的QA数据提取和分析"""
        print("🔍 开始多Agent系统QA数据分析...")
        
        try:
            # 加载数据
            history_data, node_data, trace_data = self.load_data()
            
            # 分析session模式
            session_patterns = self.analyze_session_patterns(history_data)
            
            # 提取各类QA数据
            end_to_end_qa = self.extract_end_to_end_qa(history_data)
            agent_to_agent_qa = self.extract_agent_to_agent_qa(history_data)
            node_level_qa = self.extract_node_level_qa(node_data)
            
            # 合并所有QA数据
            all_qa_items = end_to_end_qa + agent_to_agent_qa + node_level_qa
            
            # 按时间排序
            all_qa_items.sort(key=lambda x: x.timestamp or "")
            
            # 导出数据
            self.export_qa_data(all_qa_items, output_file)
            
            # 生成分析报告
            report = self.generate_analysis_report(all_qa_items, session_patterns)
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            print(f"\n✅ 数据提取和分析完成！")
            print(f"📄 QA数据已保存到: {output_file}")
            print(f"📋 分析报告已保存到: {report_file}")
            
            # 输出统计信息
            print(f"\n📊 提取统计:")
            source_counts = {}
            for item in all_qa_items:
                source_counts[item.source] = source_counts.get(item.source, 0) + 1
            
            for source, count in source_counts.items():
                print(f"  - {source}: {count} 条")
            
            return output_file, report_file
            
        except FileNotFoundError as e:
            print(f"❌ 错误: 无法找到数据文件 - {e}")
            print("请确保在OxyGent项目根目录运行此脚本")
            return None, None
        except Exception as e:
            print(f"❌ 处理过程中发生错误: {e}")
            return None, None


def main():
    """主函数"""
    extractor = SimpleMultiAgentQAExtractor()
    extractor.run_full_extraction()


if __name__ == "__main__":
    main()
