"""
论文复现系统完整测试

测试完整的论文解析流程
"""
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'backend/hermes')

import json
from backend.tools.paper_reproduction.parse_paper import parse_paper

# 测试论文解析
print("=" * 60)
print("测试论文解析工具")
print("=" * 60)

result = parse_paper.invoke({
    'paper_url': 'https://arxiv.org/abs/2009.00031'
})

data = json.loads(result)

if 'error' in data:
    print(f"\n[失败] 错误: {data['error']}")
    sys.exit(1)

print(f"\n[成功]")
print(f"  标题: {data.get('title')}")
print(f"  作者: {data.get('authors')}")
print(f"  摘要长度: {len(data.get('abstract', ''))} 字符")
print(f"  实体数量: {data.get('entities_count')}")
print(f"  关系数量: {data.get('relations_count')}")
print(f"  文本长度: {data.get('text_length')} 字符")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)