"""Mini Redis CLI (REPL).

사용법:
    python main.py            대화형 실행
    python main.py --demo     과제 예시 시나리오를 그대로 재현

`mini-redis>` 프롬프트에서 명령을 입력하면 즉시 결과가 출력되고,
`exit` 또는 `quit` 으로 종료한다.
"""

import sys
import time

from core.commands import CommandHandler
from core.store import MiniRedis

PROMPT = "mini-redis> "
BANNER = ("Mini Redis (직접 구현한 해시맵 / 이중 연결 리스트 / 최소 힙)\n"
          "HELP 로 명령어 목록, exit 또는 quit 으로 종료합니다.")


def repl():
    """명령어 파싱 -> 실행 -> 출력을 반복하는 REPL 루프."""
    engine = MiniRedis()
    handler = CommandHandler(engine)
    print(BANNER)
    while True:
        try:
            line = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        stripped = line.strip()
        if stripped.lower() in ("exit", "quit"):
            break
        reply = handler.execute_line(line)
        if reply is not None:
            print(reply.render())
    return 0


DEMO_SCRIPT = [
    "CONFIG SET maxmemory 30",
    'SET user:1 "Alice"',
    'SET user:2 "Bob"',
    'SET user:3 "Charlie"',
    "# maxmemory(30) 초과로 LRU(user:1) 자동 제거",
    "GET user:1",
    "INFO memory",
    "KEYS",
    "EXPIRE user:2 3",
    "TTL user:2",
    "# (3초 경과)",
    "@sleep 3",
    "GET user:2",
    "TTL user:2",
    "# 에러 처리 표준",
    "CONFIG SET maxmemory abc",
    "GET",
    "HELLO",
    'SET big "이 값은 maxmemory 보다 큽니다"',
]


def demo():
    """README/평가용 시나리오를 자동 실행해 출력한다."""
    engine = MiniRedis()
    handler = CommandHandler(engine)
    for line in DEMO_SCRIPT:
        if line.startswith("#"):
            print("\n" + line)
            continue
        if line.startswith("@sleep"):
            time.sleep(float(line.split()[1]))
            continue
        print(PROMPT + line)
        reply = handler.execute_line(line)
        if reply is not None:
            print(reply.render())
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "--demo":
        return demo()
    return repl()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
