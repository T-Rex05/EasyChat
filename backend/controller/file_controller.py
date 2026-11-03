"""
文件控制器 - 负责附件文件的处理和管理
"""
import os
import re
import uuid
import shutil
from typing import List, Dict, Any
from backend.utils.log_utils import log

logger = log


def rename_attachment_with_ids(file_path: str, user_id: int, thread_id: str) -> str:
    """
    重命名附件文件，在文件名后面添加uuid_userId_threadId

    格式：{original_name}_{uuid}_{user_id}_{thread_id}.{ext}

    Args:
        file_path: 原始文件路径（如 /static/charts/chart.png）
        user_id: 用户ID
        thread_id: 会话ID

    Returns:
        str: 重命名后的Web路径
    """
    # 保存原始Web路径（用于后续判断）
    original_web_path = file_path

    # 构建文件系统路径（PyInstaller 兼容）
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，使用可执行文件所在目录
        project_root = os.path.dirname(sys.executable)
    else:
        # 开发环境，使用文件路径
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    if file_path.startswith('/static/'):
        file_path = file_path[1:]  # 去掉开头的 /
    full_path = os.path.join(project_root, file_path)

    # 检查文件是否存在
    if not os.path.exists(full_path):
        logger.warning(f"文件不存在，跳过重命名: {full_path}")
        return file_path

    # 解析文件路径
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    name, ext = os.path.splitext(filename)

    # 生成新文件名：原文件名_uuid_userId_threadId.扩展名
    new_uuid = uuid.uuid4().hex[:8]
    new_filename = f"{name}_{new_uuid}_{user_id}_{thread_id}{ext}"
    new_full_path = os.path.join(directory, new_filename)

    # 重命名文件
    try:
        shutil.move(full_path, new_full_path)
        logger.info(f"文件重命名成功: {filename} → {new_filename}")

        # 返回新的Web路径（使用正斜杠，确保Web路径格式正确）
        if file_path.startswith('/static/'):
            relative_path = os.path.relpath(new_full_path, os.path.join(project_root, 'static'))
            # 将Windows反斜杠转换为正斜杠
            relative_path = relative_path.replace('\\', '/')
            return f"/static/{relative_path}"
        else:
            relative_path = os.path.relpath(new_full_path, project_root)
            # 将Windows反斜杠转换为正斜杠
            relative_path = relative_path.replace('\\', '/')
            return f"/{relative_path}"
    except Exception as e:
        logger.error(f"文件重命名失败: {e}")
        return file_path


def extract_attachments_from_output(output: str) -> List[Dict[str, Any]]:
    """
    从工具输出中提取附件路径
    支持的格式：
    - /static/charts/xxx.png
    - /static/reports/xxx.pdf
    - /static/reports/xxx.docx
    - /static/reports/xxx.xlsx
    - 图片 1: /static/charts/xxx.png (fig_inter多图格式)
    - - 拓扑图路径: /static/charts/topology_xxx.png
    """
    attachments = []

    if not output or not isinstance(output, str):
        return attachments

    # 定义文件类型映射（必须与数据库定义一致）
    # 数据库定义：1-Word 2-Excel 3-PDF 4-图片
    file_type_patterns = {
        r'\.pdf$': 3,  # PDF
        r'\.(png|jpg|jpeg|gif|svg)$': 4,  # 图片
        r'\.docx?$': 1,  # Word
        r'\.xlsx?$': 2,  # Excel
    }

    # 使用集合去重，避免重复路径
    seen_paths = set()

    # 方案1：直接匹配完整路径（最可靠）
    # 匹配 /static/charts/ 或 /static/reports/ 后跟文件名
    direct_pattern = r'(/static/(?:charts|reports)/[^\s\)\]\}\n<>"]+\.(?:png|jpg|jpeg|gif|svg|pdf|docx?|xlsx?))'
    direct_matches = re.findall(direct_pattern, output, re.IGNORECASE)
    
    for file_path in direct_matches:
        if file_path in seen_paths:
            continue
        seen_paths.add(file_path)
        
        file_ext = file_path.split('.')[-1].lower() if '.' in file_path else ''

        # 识别文件类型
        file_type = 4  # 默认为图片
        for type_pattern, type_code in file_type_patterns.items():
            if re.search(type_pattern, file_ext):
                file_type = type_code
                break

        # 提取文件名（不带扩展名）
        file_name = file_path.split('/')[-1].split('.')[0] if '/' in file_path else file_path

        attachments.append({
            'type': file_type,
            'path': file_path,
            'name': file_name
        })

    logger.debug(f"从输出中提取到 {len(attachments)} 个附件: {[a['path'] for a in attachments]}")

    return attachments


def extract_sql_records_from_output(output: str, tool_name: str = "") -> List[Dict[str, Any]]:
    """
    从工具输出中提取SQL记录（用于业务分析工具等内部执行SQL的工具）
    支持的格式：
    <!-- SQL_RECORD: {"database": "mysql", "query": "SELECT ...", "status": 2, "error": "..."} -->
    """
    sql_records = []

    if not output or not isinstance(output, str):
        return sql_records

    import json

    # 匹配 SQL_RECORD 标记
    pattern = r'<!--\s*SQL_RECORD:\s*(\{.*?\})\s*-->'

    matches = re.findall(pattern, output, re.DOTALL)
    for match in matches:
        try:
            record = json.loads(match)
            record['tool_type'] = tool_name if tool_name else 'business_analysis'
            sql_records.append(record)
        except json.JSONDecodeError as e:
            logger.warning(f"解析SQL记录失败: {e}")

    return sql_records
