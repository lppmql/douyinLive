"""本地 Embedding 服务 —— 文本转向量

使用 BAAI/bge-small-zh-v1.5 模型（中文优化，512 维，约 95MB）。
模型已通过 ModelScope 下载到本地，避免 HuggingFace 被墙问题。"""

import logging
import threading
from pathlib import Path
import torch
from transformers import AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)

# 本地已下载的模型路径（ModelScope 下载，避免 HuggingFace 被墙）
_LOCAL_MODEL = "/Users/lpp/douyinLive/data/models/models/BAAI--bge-small-zh-v1.5/snapshots/master"
MODEL_NAME = _LOCAL_MODEL if Path(_LOCAL_MODEL).is_dir() else "BAAI/bge-small-zh-v1.5"
VECTOR_DIM = 512          # bge-small-zh-v1.5 输出 512 维向量
MAX_CHARS = 512           # 模型 token 上限约 512 tokens，中文一个字 ≈ 1 token
BATCH_SIZE = 32           # 批量编码大小

# 全局模型实例（懒加载 + 线程安全）
_model: AutoModel | None = None
_tokenizer: AutoTokenizer | None = None
_model_lock = threading.Lock()


def _ensure_model() -> tuple[AutoModel, AutoTokenizer]:
    """确保模型和分词器已加载（线程安全懒加载）。"""
    global _model, _tokenizer
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("正在加载本地 embedding 模型 '%s' ...", MODEL_NAME)
                _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=Path(_LOCAL_MODEL).is_dir())
                _model = AutoModel.from_pretrained(MODEL_NAME, local_files_only=Path(_LOCAL_MODEL).is_dir())
                _model.eval()
                logger.info("Embedding 模型加载完成，向量维度=%d", VECTOR_DIM)
    return _model, _tokenizer


def _mean_pooling(model_output, attention_mask) -> torch.Tensor:
    """Mean pooling：把每个 token 的向量加权平均，得到整句话的向量。"""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)


def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    """截断过长文本，保留前后各一半。"""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + text[-half:]


def embed_text(text: str) -> list[float] | None:
    """把一段文本转成 512 维向量。

    Args:
        text: 要向量化的文本

    Returns:
        512 维向量列表（已 L2 归一化），失败返回 None
    """
    if not text or not text.strip():
        return None

    truncated = _truncate(text.strip())
    try:
        model, tokenizer = _ensure_model()
        encoded = tokenizer(truncated, padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            model_output = model(**encoded)
        embedding = _mean_pooling(model_output, encoded["attention_mask"])
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        vector = embedding[0].tolist()
        logger.debug("Embedding 成功，文本长度=%d，向量维度=%d", len(truncated), len(vector))
        return vector
    except Exception as exc:
        logger.warning("Embedding 失败: %s", exc)
        return None


def embed_batch(texts: list[str]) -> list[list[float] | None]:
    """批量把多段文本转成向量。

    Args:
        texts: 要向量化的文本列表

    Returns:
        向量列表，与 texts 一一对应
    """
    if not texts:
        return []

    valid_texts = [_truncate(t.strip()) for t in texts]
    results: list[list[float] | None] = [None] * len(texts)

    try:
        model, tokenizer = _ensure_model()
        encoded = tokenizer(valid_texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.no_grad():
            model_output = model(**encoded)
        embeddings = _mean_pooling(model_output, encoded["attention_mask"])
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        for i in range(embeddings.shape[0]):
            results[i] = embeddings[i].tolist()
        logger.debug("批量 Embedding 成功: %d 条", len(valid_texts))
    except Exception as exc:
        logger.warning("批量 Embedding 失败: %s", exc)

    return results


def embed_text_safe(text: str) -> list[float]:
    """安全版 embedding，失败时返回零向量。"""
    result = embed_text(text)
    if result is not None:
        return result
    return [0.0] * VECTOR_DIM
