"""检查后端服务的 Python 环境"""
import sys
import os

print("=" * 60)
print("后端服务 Python 环境检查")
print("=" * 60)

print("\n1. Python 可执行文件:")
print("   ", sys.executable)

print("\n2. Python 版本:")
print("   ", sys.version)

print("\n3. 工作目录:")
print("   ", os.getcwd())

print("\n4. PyPDF2 状态:")
try:
    import PyPDF2
    print("   [OK] PyPDF2 已安装")
    print("   版本:", PyPDF2.__version__)
    print("   位置:", PyPDF2.__file__)
except ImportError as e:
    print("   [ERROR] PyPDF2 未安装:", e)

print("\n5. pdfplumber 状态:")
try:
    import pdfplumber
    print("   [OK] pdfplumber 已安装")
    print("   位置:", pdfplumber.__file__)
except ImportError as e:
    print("   [ERROR] pdfplumber 未安装:", e)

print("\n" + "=" * 60)
