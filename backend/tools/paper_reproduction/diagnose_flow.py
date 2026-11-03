"""
论文复现系统诊断脚本

直接测试所有工具，检查数据流
"""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.tools.paper_reproduction.parse_paper import parse_paper
from backend.tools.paper_reproduction.extract_claim_rubric import extract_claim_rubric
from backend.tools.paper_reproduction.discover_repo import discover_repo
from backend.tools.paper_reproduction.build_evidence_graph import build_evidence_graph

print("=" * 70)
print("论文复现系统完整诊断")
print("=" * 70)

# 测试 1：论文解析
print("\n[测试 1] 论文解析")
print("-" * 70)
result1 = parse_paper.invoke({'paper_url': 'https://arxiv.org/abs/2009.00031'})
data1 = json.loads(result1)

if 'error' in data1:
    print(f"❌ 失败: {data1['error']}")
    sys.exit(1)
else:
    print(f"✅ 成功!")
    print(f"  标题: {data1.get('title')}")
    print(f"  主张: {len(data1.get('claims', []))} 个")

# 测试 2：主张提取
print("\n[测试 2] 主张提取")
print("-" * 70)
result2 = extract_claim_rubric.invoke({
    'parsed_paper': data1,
    'max_claims': 5
})
data2 = json.loads(result2)

if 'error' in data2:
    print(f"❌ 失败: {data2['error']}")
    sys.exit(1)
else:
    print(f"✅ 成功!")
    print(f"  主张数: {len(data2.get('claims', []))} 个")

    # 检查主张结构
    if data2.get('claims'):
        print(f"\n  第一个主张结构:")
        claim = data2['claims'][0]
        print(f"    ID: {claim.get('id')}")
        print(f"    标题: {claim.get('title')}")
        print(f"    准则数: {len(claim.get('criteria', []))}")

# 测试 3：证据图谱（无执行结果）
print("\n[测试 3] 证据图谱（无执行结果）")
print("-" * 70)
result3 = build_evidence_graph.invoke({
    'rubric': data2,
    'execution_results': {'status': 'no_execution'}
})
data3 = json.loads(result3)

if 'error' in data3:
    print(f"❌ 失败: {data3['error']}")
else:
    print(f"✅ 成功!")
    print(f"  节点数: {len(data3.get('graph', {}).get('nodes', []))}")
    print(f"  置信度: {json.dumps(data3.get('confidence'), indent=4)}")

    # 检查节点
    print(f"\n  节点详情:")
    for node in data3.get('graph', {}).get('nodes', [])[:5]:
        print(f"    {node.get('type')}: {node.get('id')} (status: {node.get('status')})")

# 测试 4：前端期望的数据格式
print("\n[测试 4] 前端数据格式验证")
print("-" * 70)

print("  后端返回的顶层键:", list(data3.keys()))
print("  graph 键:", list(data3.get('graph', {}).keys()))
print("  confidence 键:", list(data3.get('confidence', {}).keys()))

print("\n  前端期望接收:")
print("    evidenceGraph.graph.nodes")
print("    evidenceGraph.confidence.pending")

print("\n  实际数据:")
print(f"    nodes: {len(data3.get('graph', {}).get('nodes', []))} 个")
print(f"    pending: {data3.get('confidence', {}).get('pending', 0)}")

print("\n" + "=" * 70)
print("诊断完成!")
print("=" * 70)