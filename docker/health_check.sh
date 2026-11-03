#!/bin/bash
# Docker 容器健康检查和自动修复脚本

echo "=========================================="
echo "Docker 容器健康检查"
echo "=========================================="

# 检查容器状态
check_container() {
    local name=$1
    local status=$(docker inspect -f '{{.State.Status}}' $name 2>/dev/null)

    if [ "$status" != "running" ]; then
        echo "[ERROR] $name is not running (status: $status)"
        return 1
    fi

    local health=$(docker inspect -f '{{.State.Health.Status}}' $name 2>/dev/null)
    if [ "$health" != "healthy" ]; then
        echo "[WARN] $name is not healthy (health: $health)"
        return 1
    fi

    echo "[OK] $name is running and healthy"
    return 0
}

# 修复容器
fix_container() {
    local name=$1
    echo "[FIX] Restarting $name..."
    docker restart $name
    sleep 10

    # 如果还是失败，重新创建
    if ! check_container $name; then
        echo "[FIX] Removing and recreating $name..."
        docker rm -f $name
        docker-compose up -d $name
    fi
}

# 检查所有关键容器
containers=("agentforge-neo4j" "agentforge-milvus" "agentforge-mysql" "agentforge-redis")

for container in "${containers[@]}"; do
    if ! check_container $container; then
        fix_container $container
    fi
done

echo ""
echo "=========================================="
echo "健康检查完成"
echo "=========================================="

# 显示最终状态
docker ps | grep agentforge