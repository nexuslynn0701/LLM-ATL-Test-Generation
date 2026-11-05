#!/bin/bash
# ============================================================
# run_pipeline.sh — 实验自动化主控脚本
#
# 执行顺序：
#   1. DeepSeek三个进程暂停（等GPT跑完）
#   2. 等待 GPT_core + GPT_fl_aware_v2 完成
#   3. 恢复 DeepSeek 三个进程
#   4. 启动 GPT_mixed_v2
#   5. 等待 DeepSeek generate-only 完成 → 启动 mutation-only
#   6. 等待所有实验完成 → 跑 SBFL
#
# 使用方法：
#   nohup bash run_pipeline.sh > logs/v2/pipeline.log 2>&1 &
# ============================================================

set -uo pipefail

# 工作区根目录：可用环境变量 LLM_MT_WORK 覆盖；默认取脚本所在的 pipeline 根
# （2026-10-15 改造：原硬编码 $HOME/research/llm_mt_experiment 已不存在）
PROJ="${LLM_MT_WORK:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LOG_DIR="$PROJ/logs/v2"
DS_RESULTS="$PROJ/results_v2/deepseek"
GPT_RESULTS="$PROJ/results_v2/gpt"

# venv（Unix 布局）存在则激活；否则用当前 Python（Windows Git Bash 下 python3 常缺失）
if [ -f "$PROJ/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJ/venv/bin/activate"
fi
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/pipeline.log"
}

wait_for_pid() {
    local pid=$1
    local name=$2
    log "等待 $name (PID=$pid) 完成..."
    while kill -0 "$pid" 2>/dev/null; do
        sleep 30
    done
    log "$name (PID=$pid) 已完成"
}

wait_for_config() {
    local results_csv=$1
    local config=$2
    local expected_rows=$3
    local name=$4
    log "等待 $name 完成（预期 $expected_rows 行）..."
    while true; do
        local n
        n=$("$PY" -c "
import pandas as pd
try:
    df = pd.read_csv('$results_csv')
    print(len(df[df['config'] == '$config']))
except:
    print(0)
")
        log "$name: $n / $expected_rows 行"
        if [ "$n" -ge "$expected_rows" ]; then
            log "$name 完成"
            break
        fi
        sleep 60
    done
}

# ============================================================
# 阶段1：暂停 DeepSeek 三个进程，让 GPT 先跑
# ============================================================
log "=== 阶段1：暂停 DeepSeek 进程 ==="

DS_PIDS=()
for pid_file in \
    "$LOG_DIR/deepseek_core_v2_generate_v2.pid" \
    "$LOG_DIR/deepseek_fl_aware_v2_v2.pid" \
    "$LOG_DIR/deepseek_mixed_v2_v2.pid"; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill -STOP "$pid"
            DS_PIDS+=("$pid")
            log "暂停 $(basename $pid_file .pid) PID=$pid"
        fi
    fi
done

# ============================================================
# 阶段2：等待 GPT_core 和 GPT_fl_aware_v2 完成
# ============================================================
log "=== 阶段2：等待 GPT_core + GPT_fl_aware_v2 完成 ==="

GPT_CORE_PID=$(cat "$LOG_DIR/GPT_core_rerun4.pid" 2>/dev/null || echo "")
if [ -n "$GPT_CORE_PID" ] && kill -0 "$GPT_CORE_PID" 2>/dev/null; then
    wait_for_pid "$GPT_CORE_PID" "GPT_core rerun4"
else
    wait_for_config "$GPT_RESULTS/multi_config_results.csv" "GPT_core" 300 "GPT_core"
fi

FL_AWARE_PID=$(cat "$LOG_DIR/GPT_fl_aware_v2_rerun3.pid" 2>/dev/null || echo "")
if [ -n "$FL_AWARE_PID" ] && kill -0 "$FL_AWARE_PID" 2>/dev/null; then
    wait_for_pid "$FL_AWARE_PID" "GPT_fl_aware_v2"
else
    wait_for_config "$GPT_RESULTS/multi_config_results.csv" "GPT_fl_aware_v2" 300 "GPT_fl_aware_v2"
fi

# ============================================================
# 阶段3：恢复 DeepSeek 进程 + 启动 GPT_mixed_v2
# ============================================================
log "=== 阶段3：恢复 DeepSeek 进程 ==="

for pid in "${DS_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
        kill -CONT "$pid"
        log "恢复 PID=$pid"
    fi
done

log "=== 阶段3：启动 GPT_mixed_v2 ==="

nohup env LLM_RESULTS_DIR="$GPT_RESULTS" \
    "$PY" "$PROJ/src/experiment/run_experiment.py" --config GPT_mixed_v2 \
    > "$LOG_DIR/GPT_mixed_v2_auto.log" 2>&1 &
MIXED_PID=$!
echo $MIXED_PID > "$LOG_DIR/GPT_mixed_v2_auto.pid"
log "GPT_mixed_v2 启动 PID=$MIXED_PID"

# ============================================================
# 阶段4：等待 DeepSeek_core_v2 generate-only 完成 → 启动 mutation-only
# ============================================================
log "=== 阶段4：等待 DeepSeek generate-only 完成 ==="

CORE_GEN_PID=$(cat "$LOG_DIR/deepseek_core_v2_generate_v2.pid" 2>/dev/null || echo "")
if [ -n "$CORE_GEN_PID" ] && kill -0 "$CORE_GEN_PID" 2>/dev/null; then
    wait_for_pid "$CORE_GEN_PID" "DeepSeek_core_v2 generate-only"
else
    log "DeepSeek_core_v2 generate-only 已完成或PID不存在"
fi

log "=== 阶段4：启动 DeepSeek_core_v2 mutation-only ==="

nohup env LLM_RESULTS_DIR="$DS_RESULTS" \
    "$PY" "$PROJ/src/experiment/run_experiment.py" --config DeepSeek_core_v2 --mutation-only \
    > "$LOG_DIR/deepseek_core_v2_mutation_v2.log" 2>&1 &
MUTATION_PID=$!
echo $MUTATION_PID > "$LOG_DIR/deepseek_core_v2_mutation_v2.pid"
log "DeepSeek_core_v2 mutation-only 启动 PID=$MUTATION_PID"

# ============================================================
# 阶段5：等待所有实验完成
# ============================================================
log "=== 阶段5：等待所有实验完成 ==="

wait_for_pid "$MIXED_PID"    "GPT_mixed_v2"
wait_for_pid "$MUTATION_PID" "DeepSeek_core_v2 mutation-only"

for pid_file in \
    "$LOG_DIR/deepseek_fl_aware_v2_v2.pid" \
    "$LOG_DIR/deepseek_mixed_v2_v2.pid"; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        name=$(basename "$pid_file" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            wait_for_pid "$pid" "$name"
        fi
    fi
done

# ============================================================
# 阶段6：导出规则谱长表（rq3_test_rule_spectra_long 格式）
# 原引用的 export_sbfl_detailed.py 已不随包存在，
# 由 scripts/export_rule_spectra_long.py 顶替（2026-10-15）。
# ============================================================
log "=== 阶段6：导出规则谱长表 ==="

cd "$PROJ"
for root in "$DS_RESULTS" "$GPT_RESULTS"; do
    if [ -d "$root/outputs" ]; then
        "$PY" "$PROJ/scripts/export_rule_spectra_long.py" \
            --results-root "$root" --dataset all \
            -o "$root/rule_spectra_long.csv" 2>&1 | tee -a "$LOG_DIR/pipeline.log"
    else
        log "跳过 $root（无 outputs/ 目录）"
    fi
done

log "=== Pipeline 完成 ==="