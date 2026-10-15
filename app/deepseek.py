import os
import re

import httpx


class ModelError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


async def answer(question: str, evidence: list[dict], mode: str, history: list[dict]) -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise ModelError("未配置 DEEPSEEK_API_KEY。请在项目根目录的 .env 文件中设置后重启服务。")
    base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    if mode == "grounded":
        context = "\n\n".join(
            f"[{i + 1}] {item['title']}｜{item['stage']} {item['subject']}｜{item['edition']} {item['volume']}｜"
            f"{'PDF第' + str(item['page']) + '页' if item['page'] else '网页资料'}\n{item['text'][:950]}"
            for i, item in enumerate(evidence)
        )
        system = (
            "你是面向初高中教学的证据优先助手。先读检索片段，再把相关事实整理成通顺、直接的回答；"
            "只能根据下面的检索片段回答事实性内容。若目录和正文页同时出现，综合两者回答位置问题；"
            "每个关键结论用[1]、[2]等标记来源。教材页码只可引用明确标有PDF页码且来源类型为textbook的片段。"
            "若片段是开放网页或教学用书目录，必须明确说它不是教材正文。不能伪造课本章节、页码、引文。"
            "若证据不足，直接说明缺什么资料，并给出可继续检索的关键词。可以用分步启发引导学生思考。"
            f"\n\n检索片段：\n{context}"
        )
    else:
        system = (
            "你是初高中教学辅助助手。当前为模型常识模式，没有教材或网页证据。"
            "回答开头明确标注‘模型常识回答，未核对教材’；不得虚构教材页码、版本或引文。"
            "对不确定的事实说出不确定之处；优先给出清晰的解题思路与核验建议。"
        )
    messages = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"][:1600]})
    messages.append({"role": "user", "content": question})
    try:
        async with httpx.AsyncClient(timeout=55) as client:
            response = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.2, "stream": False},
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ModelError("DeepSeek 返回了空内容")
        if mode == "grounded":
            valid = set(range(1, len(evidence) + 1))
            content = re.sub(r"\[(\d+)\]", lambda match: match.group(0) if int(match.group(1)) in valid else "", content)
        return content.strip()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise ModelError("DeepSeek API Key 无效或已过期") from exc
        if exc.response.status_code == 429:
            raise ModelError("DeepSeek 请求频率或额度已达限制") from exc
        raise ModelError(f"DeepSeek API 返回 HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, KeyError, IndexError, ValueError) as exc:
        raise ModelError(f"DeepSeek 请求失败：{type(exc).__name__}") from exc
