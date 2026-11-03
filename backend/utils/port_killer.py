"""
端口杀死工具 - 用于在启动前杀死占用指定端口的进程
支持Linux和Windows系统
"""
import subprocess
import sys

# 设置输出编码为UTF-8
if sys.platform == 'win32':
    import io
    # 检查是否有 buffer 属性再进行操作
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def kill_port(port: int) -> bool:
    """杀死占用指定端口的进程"""
    system = sys.platform.lower()

    if system == 'win32':
        return _kill_port_windows(port)
    elif system in ('linux', 'darwin'):
        return _kill_port_unix(port)
    else:
        print(f"Unsupported OS: {system}")
        return False


def _kill_port_windows(port: int) -> bool:
    """Windows系统杀死指定端口的进程"""
    # 安全执行：使用列表参数，避免 shell=True 命令注入
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True
    )

    if not result.stdout.strip():
        print(f"Port {port} is free")
        return True

    for line in result.stdout.strip().split('\n'):
        if f':{port}' in line and 'LISTENING' in line:
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid.isdigit():
                    print(f"Killing process {pid} occupying port {port}...")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

    return True


def _kill_port_unix(port: int) -> bool:
    """Unix系统(Linux/macOS)杀死指定端口的进程"""
    # 安全执行：使用列表参数，避免 shell=True 命令注入
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True
    )

    if not result.stdout.strip():
        print(f"Port {port} is free")
        return True

    for pid in result.stdout.strip().split('\n'):
        if pid.strip().isdigit():
            print(f"Killing process {pid} occupying port {port}...")
            subprocess.run(["kill", "-9", pid.strip()], capture_output=True)

    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python port_killer.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    kill_port(port)