"""
yml
k : V

"""

import os
import yaml
from pathlib import Path
from utils.path_tool import get_abs_path


def load_env():
    """加载 .env 文件中的环境变量"""
    env_path = Path(get_abs_path(".env"))
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


def load_rag_config(config_path: str = get_abs_path("config/rag.yml"), encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_chroma_config(config_path: str = get_abs_path("config/chroma.yml"), encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_prompts_config(config_path: str = get_abs_path("config/prompts.yml"), encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_agent_config(config_path: str = get_abs_path("config/agent.yml"), encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)
    
def load_key_config(config_path: str = get_abs_path("config/key.yml"), encoding: str = "utf-8"):
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)

# 加载环境变量
load_env()

# 加载配置文件
rag_conf = load_rag_config()
key_conf = load_key_config()
chroma_conf = load_chroma_config()
agent_conf = load_agent_config()
prompts_conf = load_prompts_config()

if __name__ == '__main__':
    print(agent_conf["chat_model_name"])  # 输出对应配置
