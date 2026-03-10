"""주사위 도구 — 1~6짜리 주사위 5개를 던져 결과를 JSON 리스트로 출력."""

import json
import random


def roll_dice(n=5, sides=6):
    return [random.randint(1, sides) for _ in range(n)]


if __name__ == "__main__":
    result = roll_dice()
    print(json.dumps(result))
