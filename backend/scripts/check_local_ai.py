"""供启动脚本和环境自检复用的本地模型检查，不触发推理。"""

import argparse
import json

from app.services.ai.llm_client import get_local_ai_runtime_status, get_ollama_service_url


def main() -> int:
    parser = argparse.ArgumentParser(description="检查本地 Ollama 服务与模型")
    parser.add_argument("--service-url", action="store_true", help="只输出经过校验的本机服务地址")
    args = parser.parse_args()
    if args.service_url:
        print(get_ollama_service_url())
        return 0
    status = get_local_ai_runtime_status(timeout_seconds=3)
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["model_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
