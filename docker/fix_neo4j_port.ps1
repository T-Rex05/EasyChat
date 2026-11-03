#Requires -RunAsAdministrator
# Docker Desktop 端口映射修复脚本
# 需要 PowerShell 管理员权限运行

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Docker Desktop 端口映射修复" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Docker Desktop 状态
Write-Host "[1/5] 检查 Docker Desktop 状态..." -ForegroundColor Yellow
$dockerProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if ($dockerProcess) {
    Write-Host "  Docker Desktop 正在运行 (PID: $($dockerProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  Docker Desktop 未运行，请先启动 Docker Desktop" -ForegroundColor Red
    exit 1
}

# 2. 停止 Neo4j 容器
Write-Host ""
Write-Host "[2/5] 停止 Neo4j 容器..." -ForegroundColor Yellow
docker stop agentforge-neo4j 2>$null
docker rm agentforge-neo4j 2>$null
Write-Host "  已清理旧容器" -ForegroundColor Green

# 3. 重启 Docker 服务（WSL2）
Write-Host ""
Write-Host "[3/5] 重启 WSL2 网络栈..." -ForegroundColor Yellow
Write-Host "  这可能需要 10-20 秒..." -ForegroundColor Gray

# 重启 WSL2
wsl --shutdown
Start-Sleep -Seconds 5

# 等待 Docker Desktop 自动重启 WSL2
$maxWait = 60
$waited = 0
while (-not (Test-Path "\\wsl$\docker-desktop-data") -and $waited -lt $maxWait) {
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "." -NoNewline -ForegroundColor Gray
}
Write-Host ""

if ($waited -ge $maxWait) {
    Write-Host "  WSL2 重启超时，请手动重启 Docker Desktop" -ForegroundColor Red
    exit 1
}

Write-Host "  WSL2 已重启" -ForegroundColor Green

# 4. 重新创建 Neo4j 容器
Write-Host ""
Write-Host "[4/5] 重新创建 Neo4j 容器..." -ForegroundColor Yellow

$composePath = "$PSScriptRoot\docker-compose.yml"
if (Test-Path $composePath) {
    docker-compose -f $composePath up -d neo4j
} else {
    # 使用默认配置
    docker run -d --name agentforge-neo4j `
        --network agentforge-network `
        -p 7474:7474 -p 7687:7687 `
        -e NEO4J_server_memory_pagecache_size=256M `
        -e NEO4J_server_memory_heap_initial__size=512M `
        -e NEO4J_server_memory_heap_max__size=1G `
        -e NEO4J_dbms_security_procedures_unrestricted=apoc.* `
        -e NEO4J_dbms_security_procedures_allowlist=apoc.* `
        -v "E:/PythonCode/AgentForge/docker/volumes/neo4j/data:/data" `
        neo4j:5.15-community
}

# 等待容器启动
Start-Sleep -Seconds 10

# 5. 验证端口映射
Write-Host ""
Write-Host "[5/5] 验证端口映射..." -ForegroundColor Yellow

$containerInfo = docker ps --format "{{.Names}}\t{{.Ports}}" | Select-String "neo4j"
Write-Host "  容器信息: $containerInfo" -ForegroundColor Gray

# 检查端口映射是否生效
if ($containerInfo -match "0\.0\.0\.0:7687") {
    Write-Host "  ✅ 端口映射成功!" -ForegroundColor Green

    # 测试连接
    $neo4jTest = docker exec agentforge-neo4j cypher-shell -u neo4j -p agentforge123 "RETURN 1" 2>$null
    if ($neo4jTest) {
        Write-Host "  ✅ Neo4j 连接正常!" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ Neo4j 连接测试失败，请等待容器完全启动" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ❌ 端口映射仍然失败" -ForegroundColor Red
    Write-Host ""
    Write-Host "建议操作:" -ForegroundColor Yellow
    Write-Host "  1. 完全退出 Docker Desktop (右键 -> Quit Docker Desktop)"
    Write-Host "  2. 等待 10 秒"
    Write-Host "  3. 重新启动 Docker Desktop"
    Write-Host "  4. 运行此脚本再次尝试"
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "修复完成!" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan