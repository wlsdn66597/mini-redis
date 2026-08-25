"""Mini Redis 검증 테스트.

평가 체크리스트(항목 1~4)에 대응하도록 구성했다.

실행:
    python -m unittest discover -s tests -v
    (또는 프로젝트 루트에서)  python -m tests.test_mini_redis
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.commands import CommandHandler, tokenize          # noqa: E402
from core.store import MiniRedis                            # noqa: E402
from structures.hash_map import HashMap                     # noqa: E402
from structures.heap import MinHeap                         # noqa: E402
from structures.linked_list import DoublyLinkedList         # noqa: E402


class FakeClock:
    """테스트에서 시간을 마음대로 흐르게 하는 가짜 시계."""

    def __init__(self, start=1000.0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def new_cli(clock=None):
    """엔진 + 명령 핸들러를 만들어 (엔진, 실행함수) 로 돌려준다."""
    engine = MiniRedis(clock=clock) if clock else MiniRedis()
    handler = CommandHandler(engine)

    def run(line):
        reply = handler.execute_line(line)
        return "" if reply is None else reply.render()

    return engine, run


# ===========================================================================
# 항목 2 - 자료구조 자체 검증
# ===========================================================================
class TestDoublyLinkedList(unittest.TestCase):
    """이중 연결 리스트의 O(1) 삽입/삭제/이동."""

    def test_insert_and_order(self):
        dll = DoublyLinkedList()
        dll.insert_back("b")
        dll.insert_back("c")
        dll.insert_front("a")
        self.assertEqual(list(dll), ["a", "b", "c"])
        self.assertEqual(dll.size(), 3)

    def test_remove_front_back(self):
        dll = DoublyLinkedList()
        for ch in "abcd":
            dll.insert_back(ch)
        self.assertEqual(dll.remove_front(), "a")
        self.assertEqual(dll.remove_back(), "d")
        self.assertEqual(list(dll), ["b", "c"])

    def test_remove_node_by_reference(self):
        dll = DoublyLinkedList()
        n1 = dll.insert_back("a")
        dll.insert_back("b")
        n3 = dll.insert_back("c")
        dll.remove_node(n1)     # 탐색 없이 참조로 제거 -> O(1)
        dll.remove_node(n3)
        self.assertEqual(list(dll), ["b"])
        self.assertIs(dll.head, dll.tail)

    def test_move_to_front(self):
        dll = DoublyLinkedList()
        dll.insert_back("a")
        n_b = dll.insert_back("b")
        dll.insert_back("c")
        dll.move_to_front(n_b)
        self.assertEqual(list(dll), ["b", "a", "c"])
        self.assertEqual(dll.size(), 3)
        self.assertEqual(dll.tail.data, "c")

    def test_empty_edge_cases(self):
        dll = DoublyLinkedList()
        self.assertIsNone(dll.remove_front())
        self.assertIsNone(dll.remove_back())
        self.assertTrue(dll.is_empty())


class TestHashMap(unittest.TestCase):
    """해시 함수 / 체이닝 / 로드 팩터 확장."""

    def test_put_get_remove(self):
        hm = HashMap()
        hm.put("a", 1)
        hm.put("b", 2)
        self.assertEqual(hm.get("a"), 1)
        self.assertTrue(hm.contains("b"))
        self.assertEqual(hm.size(), 2)
        self.assertEqual(hm.remove("a"), (True, 1))
        self.assertEqual(hm.remove("a"), (False, None))
        self.assertIsNone(hm.get("a"))
        self.assertEqual(hm.size(), 1)

    def test_overwrite_keeps_size(self):
        hm = HashMap()
        hm.put("k", 1)
        hm.put("k", 2)
        self.assertEqual(hm.size(), 1)
        self.assertEqual(hm.get("k"), 2)

    def test_hash_is_deterministic_and_spread(self):
        hm = HashMap()
        self.assertEqual(hm._hash("user:1"), hm._hash("user:1"))
        self.assertNotEqual(hm._hash("user:1"), hm._hash("user:2"))
        # 1000개 키를 균등하게 뿌리는지 확인한다.
        # 이상적인(무작위) 해시라면 사용 버킷 수는 m*(1-e^(-n/m)) 에 가깝다.
        n = 1000
        for i in range(n):
            hm.put("key:%d" % i, i)
        used = 0
        longest = 0
        for bucket in hm._buckets:
            if bucket.size() > 0:
                used += 1
            if bucket.size() > longest:
                longest = bucket.size()
        m = hm.capacity()
        ideal = m * (1.0 - math.exp(-float(n) / m))
        self.assertGreater(used, ideal * 0.9)   # 쏠림 없이 고르게 분포
        self.assertLess(longest, 8)             # 특정 체인만 길어지지 않음

    def test_resize_doubles_capacity(self):
        hm = HashMap()
        start_cap = hm.capacity()
        # 로드 팩터 0.75 를 넘기면 2배 확장
        for i in range(int(start_cap * 0.75) + 1):
            hm.put("k%d" % i, i)
        self.assertEqual(hm.capacity(), start_cap * 2)
        self.assertLessEqual(hm.load_factor(), 0.75)

    def test_data_survives_resize(self):
        hm = HashMap()
        for i in range(200):
            hm.put("k%d" % i, i)
        self.assertEqual(hm.size(), 200)
        for i in range(200):
            self.assertEqual(hm.get("k%d" % i), i)
        self.assertEqual(len(hm.keys()), 200)

    def test_chaining_on_forced_collision(self):
        """버킷 수를 1로 두면 모든 키가 한 체인에 몰린다(= 체이닝 동작 확인)."""
        hm = HashMap(capacity=1)
        hm._capacity = 1
        for i in range(5):
            hm.put("k%d" % i, i)
        for i in range(5):
            self.assertEqual(hm.get("k%d" % i), i)


class TestMinHeap(unittest.TestCase):
    """최소 힙의 push/pop/peek 및 (expire_at, key) 처리."""

    def test_pop_returns_sorted_order(self):
        heap = MinHeap()
        for v in [5, 3, 8, 1, 9, 2]:
            heap.push(v)
        out = []
        while heap.size():
            out.append(heap.pop())
        self.assertEqual(out, [1, 2, 3, 5, 8, 9])

    def test_peek_does_not_remove(self):
        heap = MinHeap()
        heap.push(10)
        heap.push(4)
        self.assertEqual(heap.peek(), 4)
        self.assertEqual(heap.size(), 2)

    def test_expire_tuples(self):
        heap = MinHeap()
        heap.push((1030.0, "b"))
        heap.push((1005.0, "a"))
        heap.push((1099.0, "c"))
        self.assertEqual(heap.peek(), (1005.0, "a"))
        self.assertEqual(heap.pop()[1], "a")
        self.assertEqual(heap.pop()[1], "b")

    def test_empty(self):
        heap = MinHeap()
        self.assertIsNone(heap.pop())
        self.assertIsNone(heap.peek())
        self.assertTrue(heap.is_empty())


# ===========================================================================
# 항목 1 - String 기본 동작 / LRU / INFO / TTL / 에러 처리
# ===========================================================================
class TestStringCommands(unittest.TestCase):

    def setUp(self):
        self.engine, self.run = new_cli()

    def test_set_get(self):
        self.assertEqual(self.run('SET user:1 "Alice"'), "OK")
        self.assertEqual(self.run("GET user:1"), '"Alice"')

    def test_get_missing(self):
        self.assertEqual(self.run("GET nope"), "(nil)")

    def test_del(self):
        self.run("SET k v")
        self.assertEqual(self.run("DEL k"), "(integer) 1")
        self.assertEqual(self.run("DEL k"), "(integer) 0")
        self.assertEqual(self.run("GET k"), "(nil)")

    def test_exists(self):
        self.run("SET k v")
        self.assertEqual(self.run("EXISTS k"), "(integer) 1")
        self.assertEqual(self.run("EXISTS zzz"), "(integer) 0")

    def test_dbsize(self):
        self.assertEqual(self.run("DBSIZE"), "(integer) 0")
        self.run("SET a 1")
        self.run("SET b 2")
        self.assertEqual(self.run("DBSIZE"), "(integer) 2")

    def test_keys(self):
        self.assertEqual(self.run("KEYS"), "(empty array)")
        self.run('SET user:2 "Bob"')
        self.run('SET user:3 "Charlie"')
        out = self.run("KEYS")
        self.assertIn('"user:2"', out)
        self.assertIn('"user:3"', out)
        self.assertEqual(len(out.split("\n")), 2)

    def test_quoted_value_with_space(self):
        self.run('SET name "Alice Kim"')
        self.assertEqual(self.run("GET name"), '"Alice Kim"')

    def test_commands_are_case_insensitive(self):
        self.assertEqual(self.run("set k v"), "OK")
        self.assertEqual(self.run("get k"), '"v"')

    def test_overwrite_updates_memory(self):
        self.run("SET k aaaaa")          # 1 + 5
        self.assertEqual(self.engine.used_memory, 6)
        self.run("SET k b")              # 1 + 1
        self.assertEqual(self.engine.used_memory, 2)


class TestLruEviction(unittest.TestCase):
    """항목 1: maxmemory 초과 시 가장 오래된 키 자동 제거."""

    def setUp(self):
        self.engine, self.run = new_cli()

    def test_assignment_example_scenario(self):
        """과제 예시 시나리오를 그대로 재현한다."""
        self.assertEqual(self.run("CONFIG SET maxmemory 30"), "OK")
        self.run('SET user:1 "Alice"')     # 6 + 5 = 11
        self.run('SET user:2 "Bob"')       # 6 + 3 = 9   (누적 20)
        self.run('SET user:3 "Charlie"')   # 6 + 7 = 13  (누적 33 > 30)
        self.assertEqual(self.run("GET user:1"), "(nil)")   # LRU 제거됨
        self.assertEqual(self.run("INFO memory"),
                         "used_memory:22\nmaxmemory:30\nevicted_keys:1")
        out = self.run("KEYS")
        self.assertIn('"user:2"', out)
        self.assertIn('"user:3"', out)

    def test_get_refreshes_lru_order(self):
        self.run("CONFIG SET maxmemory 0")
        self.run("SET a 1")
        self.run("SET b 2")
        self.run("SET c 3")
        self.assertEqual(self.engine.lru_order(), ["c", "b", "a"])
        self.run("GET a")                 # a 를 최신으로 끌어올림
        self.assertEqual(self.engine.lru_order(), ["a", "c", "b"])

    def test_recently_used_key_survives_eviction(self):
        self.run("CONFIG SET maxmemory 12")
        self.run("SET aa 11")             # 4
        self.run("SET bb 22")             # 4 (누적 8)
        self.run("GET aa")                # aa 가 최신 -> bb 가 최고참
        self.run("SET cc 33")             # 누적 12 (아직 초과 아님)
        self.run("SET dd 44")             # 16 > 12 -> bb 제거
        self.assertEqual(self.run("EXISTS bb"), "(integer) 0")
        self.assertEqual(self.run("EXISTS aa"), "(integer) 1")
        self.assertEqual(self.engine.evicted_keys, 1)

    def test_multiple_evictions_in_one_set(self):
        self.run("CONFIG SET maxmemory 10")
        self.run("SET a 1")               # 2
        self.run("SET b 2")               # 4
        self.run("SET c 3")               # 6
        self.run("SET dddd 4444")         # 8 -> 누적 14 > 10, a,b 제거 -> 10
        self.assertEqual(self.engine.used_memory, 10)
        self.assertEqual(self.engine.evicted_keys, 2)
        self.assertEqual(self.run("EXISTS a"), "(integer) 0")
        self.assertEqual(self.run("EXISTS b"), "(integer) 0")
        self.assertEqual(self.run("EXISTS c"), "(integer) 1")

    def test_single_entry_larger_than_maxmemory_is_oom(self):
        self.run("CONFIG SET maxmemory 5")
        self.assertEqual(
            self.run('SET key "너무 큰 값"'),
            "(error) OOM command not allowed when used_memory > 'maxmemory'")
        self.assertEqual(self.run("DBSIZE"), "(integer) 0")
        self.assertEqual(self.engine.used_memory, 0)

    def test_maxmemory_zero_is_unlimited(self):
        self.run("CONFIG SET maxmemory 0")
        for i in range(50):
            self.run("SET k%d v%d" % (i, i))
        self.assertEqual(self.run("DBSIZE"), "(integer) 50")
        self.assertEqual(self.engine.evicted_keys, 0)

    def test_used_memory_counts_utf8_bytes(self):
        self.run('SET 이름 "값"')          # 한글 1자 = 3바이트 -> 6 + 3
        self.assertEqual(self.engine.used_memory, 9)

    def test_lowering_maxmemory_triggers_eviction(self):
        self.run("SET aa 11")
        self.run("SET bb 22")
        self.run("CONFIG SET maxmemory 4")
        self.assertEqual(self.engine.used_memory, 4)
        self.assertEqual(self.engine.evicted_keys, 1)


class TestInfoMemory(unittest.TestCase):
    """항목 1: INFO memory 출력 규격."""

    def test_format(self):
        engine, run = new_cli()
        self.assertEqual(run("INFO memory"),
                         "used_memory:0\nmaxmemory:0\nevicted_keys:0")
        run("CONFIG SET maxmemory 100")
        run("SET a bb")
        self.assertEqual(run("INFO"),
                         "used_memory:3\nmaxmemory:100\nevicted_keys:0")

    def test_used_memory_returns_to_zero_after_del(self):
        engine, run = new_cli()
        run('SET user:1 "Alice"')
        run("DEL user:1")
        self.assertEqual(engine.used_memory, 0)


class TestTtl(unittest.TestCase):
    """항목 1/3: EXPIRE / TTL 및 만료 처리."""

    def setUp(self):
        self.clock = FakeClock()
        self.engine, self.run = new_cli(clock=self.clock)

    def test_expire_and_ttl(self):
        self.run('SET user:2 "Bob"')
        self.assertEqual(self.run("EXPIRE user:2 3"), "(integer) 1")
        self.clock.advance(1)
        self.assertEqual(self.run("TTL user:2"), "(integer) 2")

    def test_key_disappears_after_expiry(self):
        self.run('SET user:2 "Bob"')
        self.run("EXPIRE user:2 3")
        self.clock.advance(3)
        self.assertEqual(self.run("GET user:2"), "(nil)")
        self.assertEqual(self.run("TTL user:2"), "(integer) -2")
        self.assertEqual(self.run("DBSIZE"), "(integer) 0")
        self.assertEqual(self.engine.used_memory, 0)

    def test_ttl_without_expire_is_minus_one(self):
        self.run("SET k v")
        self.assertEqual(self.run("TTL k"), "(integer) -1")

    def test_ttl_missing_key_is_minus_two(self):
        self.assertEqual(self.run("TTL nope"), "(integer) -2")

    def test_expire_missing_key_is_zero(self):
        self.assertEqual(self.run("EXPIRE nope 10"), "(integer) 0")

    def test_expire_zero_deletes_immediately(self):
        self.run("SET k v")
        self.assertEqual(self.run("EXPIRE k 0"), "(integer) 1")
        self.assertEqual(self.run("EXISTS k"), "(integer) 0")

    def test_set_overwrite_clears_ttl(self):
        self.run("SET k v")
        self.run("EXPIRE k 10")
        self.run("SET k v2")                       # 덮어쓰기 -> TTL 초기화
        self.assertEqual(self.run("TTL k"), "(integer) -1")
        self.clock.advance(20)
        self.assertEqual(self.run("GET k"), '"v2"')

    def test_expired_get_does_not_refresh_lru(self):
        self.run("SET a 1")
        self.run("SET b 2")
        self.run("EXPIRE a 1")
        self.clock.advance(2)
        self.assertEqual(self.run("GET a"), "(nil)")
        self.assertEqual(self.engine.lru_order(), ["b"])

    def test_del_removes_ttl_entry_too(self):
        self.run("SET k v")
        self.run("EXPIRE k 10")
        self.run("DEL k")
        self.run("SET k v")                        # 같은 키를 다시 생성
        self.assertEqual(self.run("TTL k"), "(integer) -1")
        self.clock.advance(20)
        self.assertEqual(self.run("GET k"), '"v"')  # 예전 TTL이 살아나면 안 됨

    def test_active_expire_cycle_uses_heap_root(self):
        self.run("SET a 1")
        self.run("SET b 2")
        self.run("EXPIRE a 5")
        self.run("EXPIRE b 10")
        self.clock.advance(6)
        self.assertEqual(self.engine.active_expire_cycle(), 1)  # a 만 제거
        self.assertEqual(self.run("EXISTS b"), "(integer) 1")

    def test_expired_key_frees_memory_for_new_data(self):
        self.run("CONFIG SET maxmemory 8")
        self.run("SET aa 11")
        self.run("EXPIRE aa 5")
        self.clock.advance(6)
        self.run("SET bb 22")
        self.run("SET cc 33")
        self.assertEqual(self.engine.evicted_keys, 0)   # 만료로 자리가 났으므로
        self.assertEqual(self.engine.used_memory, 8)


# ===========================================================================
# 항목 1 - 에러 처리 표준 / CLI 파싱
# ===========================================================================
class TestErrorHandling(unittest.TestCase):

    def setUp(self):
        self.engine, self.run = new_cli()

    def test_unknown_command(self):
        self.assertEqual(self.run("HELLO"), "(error) ERR unknown command 'HELLO'")

    def test_wrong_arity(self):
        self.assertEqual(
            self.run("GET"),
            "(error) ERR wrong number of arguments for 'GET' command")
        self.assertEqual(
            self.run("SET only_key"),
            "(error) ERR wrong number of arguments for 'SET' command")

    def test_not_an_integer(self):
        self.assertEqual(self.run("CONFIG SET maxmemory abc"),
                         "(error) ERR value is not an integer or out of range")
        self.assertEqual(self.run("EXPIRE k xyz"),
                         "(error) ERR value is not an integer or out of range")

    def test_negative_maxmemory(self):
        self.assertEqual(self.run("CONFIG SET maxmemory -1"),
                         "(error) ERR value is not an integer or out of range")

    def test_unknown_config_parameter(self):
        self.assertTrue(self.run("CONFIG SET appendonly yes").startswith("(error) ERR"))

    def test_empty_line(self):
        self.assertEqual(self.run("   "), "")

    def test_tokenizer(self):
        self.assertEqual(tokenize('SET user:1 "Alice"'), ["SET", "user:1", "Alice"])
        self.assertEqual(tokenize('SET k "a b  c"'), ["SET", "k", "a b  c"])
        self.assertEqual(tokenize('SET k ""'), ["SET", "k", ""])
        self.assertEqual(tokenize("  GET   k  "), ["GET", "k"])
        self.assertEqual(tokenize(""), [])

    def test_unbalanced_quotes(self):
        self.assertTrue(self.run('SET k "unclosed').startswith("(error) ERR Protocol error"))


# ===========================================================================
# 항목 4 - 구조적 성질(확장 질문 근거)
# ===========================================================================
class TestScaleAndConsistency(unittest.TestCase):

    def test_10k_keys_stay_consistent(self):
        engine, run = new_cli()
        for i in range(10000):
            run("SET key:%d value:%d" % (i, i))
        self.assertEqual(run("DBSIZE"), "(integer) 10000")
        self.assertEqual(run("GET key:9999"), '"value:9999"')
        self.assertEqual(len(engine.lru_order()), 10000)

    def test_memory_accounting_is_exact_after_churn(self):
        engine, run = new_cli()
        for i in range(500):
            run("SET k%d v%d" % (i, i))
        for i in range(0, 500, 2):
            run("DEL k%d" % i)
        expected = 0
        for key in engine.keys():
            expected += len(key.encode("utf-8")) + len(engine.get(key).encode("utf-8"))
        self.assertEqual(engine.used_memory, expected)

    def test_lru_list_and_hashmap_stay_in_sync(self):
        engine, run = new_cli()
        run("CONFIG SET maxmemory 40")
        for i in range(200):
            run("SET k%d v%d" % (i, i))
            run("GET k%d" % (i // 2))
        self.assertEqual(len(engine.lru_order()), int(run("DBSIZE").split()[-1]))
        self.assertLessEqual(engine.used_memory, 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
