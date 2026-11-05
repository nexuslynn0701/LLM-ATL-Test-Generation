#!/usr/bin/env bash
# auto_sbfl_v2.sh
# 等待九个 v2 实验进程全部完成后，自动计算 SBFL 和指标表

# 工作区根目录：可用环境变量 LLM_MT_WORK 覆盖；默认取脚本所在的 pipeline 根
# （2026-10-15 改造：原硬编码 $HOME/research/llm_mt_experiment 已不存在）
WORK_DIR="${LLM_MT_WORK:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOG="$WORK_DIR/logs/auto_sbfl_v2.log"
POLL=60

# venv（Unix 布局）存在则激活；否则用当前 Python（Windows Git Bash 下 python3 常缺失）
if [ -f "$WORK_DIR/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$WORK_DIR/venv/bin/activate"
fi
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

CONFIGS=(
    DeepSeek_core_v2 DeepSeek_fl_aware_v2 DeepSeek_mixed_v2
    QWEN_core_v2 QWEN_fl_aware_v2 QWEN_mixed_v2
    GPT_core GPT_fl_aware_v2 GPT_mixed_v2
)

METHODS=(
    DeepSeek_core_v2 DeepSeek_fl_aware_v2 DeepSeek_mixed_v2
    QWEN_core_v2 QWEN_fl_aware_v2 QWEN_mixed_v2
    GPT_core GPT_fl_aware_v2 GPT_mixed_v2
)

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$LOG"; }

is_done() {
    local config=$1
    tail -1 "$WORK_DIR/logs/v2/${config}_gen.log" 2>/dev/null | grep -q "\[DONE\]"
}

cd "$WORK_DIR"

log "=== auto_sbfl_v2.sh 启动，等待九个进程完成 ==="

while true; do
    all_done=true
    for config in "${CONFIGS[@]}"; do
        if ! is_done "$config"; then
            all_done=false
            last=$(tail -1 "$WORK_DIR/logs/v2/${config}_gen.log" 2>/dev/null)
            log "  等待 $config: $last"
        fi
    done

    if $all_done; then
        log "=== 所有进程完成，开始计算 SBFL ==="
        break
    fi

    sleep $POLL
done

# 按方法名推断其结果根（v2 布局：DeepSeek* → results_v2/deepseek，其余 → results_v2/gpt）
root_for_method() {
    case "$1" in
        DeepSeek*) echo "$WORK_DIR/results_v2/deepseek" ;;
        *)         echo "$WORK_DIR/results_v2/gpt" ;;
    esac
}

# 计算 SBFL：导出规则谱长表（替代已缺失的 export_sbfl_detailed.py）
for method in "${METHODS[@]}"; do
    log "计算 SBFL: $method"
    "$PY" "$WORK_DIR/scripts/export_rule_spectra_long.py" \
        --results-root "$(root_for_method "$method")" \
        --method "$method" --dataset all >> "$LOG" 2>&1
    log "完成: $method"
done

# 计算消融 SBFL（如果已跑）


# 生成统一指标表（该脚本未随包迁移；存在时才执行）
if [ -f "$WORK_DIR/scripts/compute_metrics_summary.py" ]; then
    log "生成 metrics_summary..."
    "$PY" "$WORK_DIR/scripts/compute_metrics_summary.py" >> "$LOG" 2>&1
else
    log "跳过 metrics_summary（scripts/compute_metrics_summary.py 不在包内）"
fi

# 启动消融实验
log "=== 启动消融实验 ==="

for config in ABL_v2_no_atl ABL_v2_no_target ABL_v2_no_coverage ABL_v2_no_ocl; do
    log "启动 $config"
    nohup env LLM_RESULTS_DIR="$WORK_DIR/results_v2/deepseek"         "$PY" "$WORK_DIR/src/experiment/run_experiment.py" --config "$config"         > "$WORK_DIR/logs/v2/${config}_gen.log" 2>&1 &
    log "$config PID: $!"
done

log "=== 消融实验已启动，等待完成 ==="

ABL_CONFIGS=(ABL_v2_no_atl ABL_v2_no_target ABL_v2_no_coverage ABL_v2_no_ocl)

while true; do
    all_done=true
    for config in "${ABL_CONFIGS[@]}"; do
        if ! tail -1 "$WORK_DIR/logs/v2/${config}_gen.log" 2>/dev/null | grep -q "\[DONE\]"; then
            all_done=false
            log "  等待 $config: $(tail -1 "$WORK_DIR/logs/v2/${config}_gen.log" 2>/dev/null)"
        fi
    done
    $all_done && break
    sleep $POLL
done

log "=== 消融实验完成，计算消融 SBFL ==="
for method in ABL_v2_no_atl ABL_v2_no_target ABL_v2_no_coverage ABL_v2_no_ocl; do
    log "计算 SBFL: $method"
    "$PY" "$WORK_DIR/scripts/export_rule_spectra_long.py" \
        --results-root "$(root_for_method "$method")" \
        --method "$method" --dataset all >> "$LOG" 2>&1
    log "完成: $method"
done

if [ -f "$WORK_DIR/scripts/compute_metrics_summary.py" ]; then
    "$PY" "$WORK_DIR/scripts/compute_metrics_summary.py" >> "$LOG" 2>&1
fi

log "=== 全部完成 ==="
# 注意：这行之前的内容已存在，以下是追加内容
