# v36.0 (2026-10-05) — 36aigame
# 版本: v20.0 (2025-10-03)
# -*- coding: utf-8 -*-
# 11aigame 统一部署配置
# 版本: v20.0 (2025-10-03)
# 更新: 高级集群作战调度系统
#
# 所有组件通过环境变量读取本文件导出的配置。
# 全部有默认值,零配置可跑(标准 4 卡部署)。
#
# 用法:
#     source config/env.sh          # bash
#     # 或: set -a; . config/env.sh; set +a

# --- 模型 (三帅+军师共用) ---
export TANK_MODEL="${TANK_MODEL:-/media/ibm/软件/models/Ornith-1.5-35B-Q4_K_M.gguf}"
export LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-$HOME/llama.cpp/build-hip/bin/llama-server}"

# --- 魏军三帅 LLM 端口 (曹操/夏侯惇/夏侯渊) ---
export TANK_AI_PORT_1="${TANK_AI_PORT_1:-8080}"
export TANK_AI_PORT_2="${TANK_AI_PORT_2:-8081}"
export TANK_AI_PORT_3="${TANK_AI_PORT_3:-8082}"

# --- 三帅各自绑定的 GPU (ROCm/HIP) ---
export TANK_GPU_1="${TANK_GPU_1:-0}"
export TANK_GPU_2="${TANK_GPU_2:-1}"
export TANK_GPU_3="${TANK_GPU_3:-2}"

# --- 吕布·35B 军师 (谋略层: ideal_dist/style/threat 参数包) ---
export TANK_ADVISOR_PORT="${TANK_ADVISOR_PORT:-8083}"
export TANK_ADVISOR_URL="${TANK_ADVISOR_URL:-http://127.0.0.1:${TANK_ADVISOR_PORT}/v1/chat/completions}"
export TANK_ADVISOR_GPU="${TANK_ADVISOR_GPU:-2}"       # 与三帅共卡时用 exps=CPU
export TANK_ADVISOR_CTX="${TANK_ADVISOR_CTX:-8192}"
export TANK_ADVISOR_EXTRA_ARGS="${TANK_ADVISOR_EXTRA_ARGS:--ot exps=CPU --threads 8}"

# --- 吕布·Laya 哨兵 (System-1 神经打分, ggmlc 运行时) ---
export LAYA_BIN="${LAYA_BIN:-$HOME/ggmlc/laya}"
export LAYA_MODEL="${LAYA_MODEL:-$HOME/models/laya_english_q8_0.gguf}"
export LAYA_PORT="${LAYA_PORT:-8091}"
export LAYA_URL="${LAYA_URL:-http://127.0.0.1:${LAYA_PORT}/v1/systemone}"

# --- pilot 指令 UDP 端口 ---
export TANK_UDP_PORT="${TANK_UDP_PORT:-8089}"

# --- 运行时文件目录 (遥测/日志/截图) ---
export TANK_RUNTIME_DIR="${TANK_RUNTIME_DIR:-/tmp}"

# --- 进化存档目录 (三帅大脑跨局继承; 默认仓库内 config/) ---
export TANK_EVO_DIR="${TANK_EVO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# --- 上下文长度 / GPU 层数 ---
export TANK_CTX="${TANK_CTX:-16384}"
export TANK_NGL="${TANK_NGL:-999}"
