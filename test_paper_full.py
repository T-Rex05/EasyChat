"""
论文复现系统完整测试
"""
import sys
sys.path.insert(0, '.')

import json
from backend.tools.paper_reproduction.parse_paper import parse_paper
from backend.tools.paper_reproduction.extract_claim_rubric import extract_claim_rubric
from backend.tools.paper_reproduction.discover_repo import discover_repo

print("=" * 60)
print("论文复现系统完整测试")
print("=" * 60)

# 测试 1：论文解析
print("\n[测试 1] 论文解析")
print("-" * 60)
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
    print(f"  主张: {len(data1.get('claims', []))} 个")

# 测试 2：主张提取
print("\n[测试 2] 主张提取")
print("-" * 60)
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

# 测试 3：仓库发现
print("\n[测试 3] 仓库发现")
print("-" * 60)
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
        for i, repo in enumerate(data3['repos'][:3], 1):
            print(f"  {i}. {repo.get('full_name')} (⭐ {repo.get('stars', 0)})")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)