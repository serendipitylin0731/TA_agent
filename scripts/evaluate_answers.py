"""Exercise real chat answers across subjects and absent-evidence cases.

Requires DEEPSEEK_API_KEY in .env. This sends the listed questions to the
configured model and prints compact, reviewable results; it does not grade
natural language answers as automatically correct.
"""

import asyncio

from app.main import ChatRequest, chat


CASES = [
    ("数学", "函数的定义是什么？"),
    ("数学", "椭圆的第二定义是什么？"),
    ("物理", "动量守恒定律是什么？"),
    ("生物学", "光合作用的基本过程是什么？"),
    ("化学", "中和反应是什么？"),
    ("地理", "水循环的过程是什么？"),
    ("历史", "中国古代科举制度如何发展？"),
    ("道德与法治", "法律的特征有哪些？"),
    ("思想政治", "社会主义核心价值观有哪些？"),
    ("信息技术", "算法有哪些基本特征？"),
    ("通用技术", "什么是设计的一般原则？"),
    ("通用技术", "设计的一般原则有哪些？"),
    ("", "量子计算机如何制造？"),
    ("", "完全不存在的玄月青铜定律是什么？"),
]


async def run_case(subject: str, question: str, gate: asyncio.Semaphore):
    async with gate:
        try:
            data = await chat(ChatRequest(query=question, subject=subject))
            return subject, question, data
        except Exception as exc:
            return subject, question, {"error": f"{type(exc).__name__}: {exc}"}


async def main():
    gate = asyncio.Semaphore(2)
    results = await asyncio.gather(*(run_case(subject, question, gate) for subject, question in CASES))
    for subject, question, result in results:
        citations = ", ".join(f"{item['subject']} p{item['page']}" for item in result.get("citations", []))
        print(f"[{subject or '通用'}] {question}\n  mode={result.get('mode')} evidence={result.get('evidence_status')} refs={citations or '-'}\n  {result.get('answer', result.get('error', ''))[:500]}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
