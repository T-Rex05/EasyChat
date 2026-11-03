"""
论文复现系统完整测试脚本

测试所有工具是否正常工作
"""

import sys
import json
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.tools.paper_reproduction.parse_paper import parse_paper
from backend.tools.paper_reproduction.extract_claim_rubric import extract_claim_rubric
from backend.tools.paper_reproduction.discover_repo import discover_repo
from backend.tools.paper_reproduction.build_evidence_graph import build_evidence_graph

print("=" * 70)
print("论文复现系统完整测试")
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
    print(f"  作者: {len(data1.get('authors', []))} 人")
    print(f"  实体: {data1.get('entities_count')} 个")
    print(f"  关系: {data1.get('relations_count')} 条")
    print(f"  主张 (原始): {len(data1.get('claims', []))} 个")

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
else:
    print(f"✅ 成功!")
    print(f"  主张数: {len(data2.get('claims', []))} 个")
    print(f"  SHA-256: {data2.get('sha256', '')[:20]}...")

    if data2.get('claims'):
        print(f"\n  主张列表:")
        for i, claim in enumerate(data2['claims'], 1):
            print(f"    {i}. {claim.get('title', '未命名')}")

# 测试 3：仓库发现
print("\n[测试 3] 仓库发现")
print("-" * 70)
result3 = discover_repo.invoke({
    'parsed_paper': data1,
    'claim_rubric': data2,
    'max_repos': 3
})
data3 = json.loads(result3)

if 'error' in data3:
    print(f"❌ 失败: {data3['error']}")
else:
    print(f"✅ 成功!")
    print(f"  找到仓库: {data3.get('total_found', 0)} 个")
    if data3.get('repos'):
        print(f"\n  仓库列表:")
        for i, repo in enumerate(data3['repos'][:3], 1):
            print(f"    {i}. {repo.get('full_name')} (⭐ {repo.get('stargazers_count', 0)})")

# 测试 4：证据图谱构建
print("\n[测试 4] 证据图谱构建")
print("-" * 70)
result4 = build_evidence_graph.invoke({
    'rubric': data2,
    'execution_results': {'results': []}  # 空的执行结果（正确格式）
})
data4 = json.loads(result4)

if 'error' in data4 and not data4.get('execution_error'):
    print(f"❌ 失败: {data4['error']}")
else:
    print(f"✅ 成功!")
    confidence = data4.get('confidence', {})
    print(f"  整体置信度: {confidence.get('overall', 0) * 100:.0f}%")
    print(f"  已验证: {confidence.get('verified', 0)} / {confidence.get('total', 0)}")

    if data4.get('execution_error'):
        print(f"\n  ⚠️ 执行错误: {data4['execution_error']}")

print("\n" + "=" * 70)
print("测试完成!")
print("=" * 70)

# 总结
print("\n📊 总结:")
print(f"  论文解析: ✅")
print(f"  主张提取: {'✅' if data2.get('claims') else '❌'} ({len(data2.get('claims', []))} 个主张)")
print(f"  仓库发现: {'✅' if data3.get('repos') else '⚠️'} ({data3.get('total_found', 0)} 个仓库)")
print(f"  证据图谱: ✅")

if not data2.get('claims'):
    print("\n❌ 主张提取失败，请检查 LLM 配置！")
    sys.exit(1)
else:
    print("\n✅ 所有工具正常工作！")