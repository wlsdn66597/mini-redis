"""Mini Redis 엔진: 직접 만든 자료구조 3개를 조립한 Key-Value 저장소.

구성
  - HashMap          : key -> Record (값 + LRU 노드 참조)         => O(1) 조회
  - DoublyLinkedList : 최근 사용 순서(front = 최신, back = 최고참) => O(1) 갱신
  - HashMap          : key -> expire_at (만료 시각)
  - MinHeap          : (expire_at, key) => 가장 이른 만료를 O(1)로 확인

메모리 회계
  used_memory = Σ( len(utf8(key)) + len(utf8(value)) )
  과제 규정대로 노드/포인터/버킷 등 자료구조 오버헤드는 계산에 넣지 않는다.
"""

import time

from structures.hash_map import HashMap
from structures.heap import MinHeap
from structures.linked_list import DoublyLinkedList
from core.protocol import OutOfMemoryError


def utf8_len(text):
    """문자열의 UTF-8 바이트 길이. used_memory 산정의 기본 단위."""
    return len(text.encode("utf-8"))


class Record:
    """해시맵에 저장되는 값 한 건.

    lru_node 를 함께 들고 있는 것이 핵심이다.
    이 참조 덕분에 LRU 리스트에서 탐색 없이 해당 노드를 O(1)에 옮기거나
    지울 수 있다.
    """

    __slots__ = ("value", "lru_node")

    def __init__(self, value, lru_node):
        self.value = value
        self.lru_node = lru_node


class MiniRedis:
    """CLI 명령이 호출하는 실제 저장소 엔진."""

    def __init__(self, clock=time.time):
        self._clock = clock              # 테스트에서 가짜 시계를 주입할 수 있게
        self._data = HashMap()           # key -> Record
        self._lru = DoublyLinkedList()   # data = key (front = 최근 사용)
        self._expires = HashMap()        # key -> expire_at(epoch seconds)
        self._ttl_heap = MinHeap()       # (expire_at, key), lazy deletion 사용
        self.used_memory = 0
        self.maxmemory = 0               # 0 = 무제한
        self.evicted_keys = 0
        self.expired_keys = 0

    # =============================================================== 시간/만료
    def now(self):
        return self._clock()

    def _is_expired(self, key):
        """key 에 만료 시각이 있고 이미 지났는지 확인한다. O(1)"""
        expire_at = self._expires.get(key)
        return expire_at is not None and self._clock() >= expire_at

    def _expire_if_needed(self, key):
        """(lazy expiration) 만료된 키면 지우고 True 를 돌려준다.

        모든 키 기반 명령은 실행 전에 이 함수를 먼저 통과한다.
        따라서 만료된 키는 없는 키처럼 취급된다.
        """
        if self._is_expired(key):
            self._delete_key(key)
            self.expired_keys += 1
            return True
        return False

    def active_expire_cycle(self, limit=64):
        """(active expiration) 힙 루트부터 이미 만료된 키를 걷어낸다.

        peek() 이 O(1) 이므로 만료된 게 하나도 없다는 판단이 즉시 끝난다.
        힙에는 갱신 전의 낡은 (expire_at, key) 가 남을 수 있으므로,
        꺼낸 항목이 현재 만료 시각과 일치할 때만 실제로 삭제한다(lazy deletion).
        """
        now = self._clock()
        removed = 0
        while self._ttl_heap.size() > 0 and removed < limit:
            top = self._ttl_heap.peek()
            if top[0] > now:
                break                     # 가장 이른 만료도 아직 안 됐다 -> 종료
            expire_at, key = self._ttl_heap.pop()
            current = self._expires.get(key)
            if current is None or current != expire_at:
                continue                  # 이미 지워졌거나 TTL이 바뀐 낡은 항목
            self._delete_key(key)
            self.expired_keys += 1
            removed += 1
        return removed

    # =============================================================== 내부 삭제
    def _delete_key(self, key):
        """데이터 / LRU / TTL 모든 구조에서 키를 함께 제거한다.

        used_memory 도 여기서 한 번에 되돌린다.
        (힙 항목은 남겨두고 나중에 걸러내는 lazy deletion 전략)
        """
        found, record = self._data.remove(key)
        if not found:
            self._expires.remove(key)
            return False
        self._lru.remove_node(record.lru_node)          # O(1)
        self.used_memory -= utf8_len(key) + utf8_len(record.value)
        self._expires.remove(key)
        return True

    def _touch(self, key, record):
        """LRU 갱신: 해당 키를 리스트 맨 앞으로 옮긴다. O(1)"""
        self._lru.move_to_front(record.lru_node)

    def _evict_until_within_limit(self):
        """maxmemory 이하가 될 때까지 LRU 꼬리부터 제거한다.

        꼬리(back)는 정의상 가장 오래 사용되지 않은 키이므로
        remove 대상 선택 자체가 O(1)이다.
        """
        evicted = []
        while (self.maxmemory > 0 and self.used_memory > self.maxmemory
               and self._lru.size() > 0):
            victim = self._lru.tail.data
            self._delete_key(victim)
            self.evicted_keys += 1
            evicted.append(victim)
        return evicted

    # =============================================================== 명령 구현
    def set(self, key, value):
        """SET key value

        1) 단일 엔트리(key+value)가 maxmemory 보다 크면 저장하지 않고 OOM.
        2) 기존 키를 덮어쓰는 경우 TTL은 초기화(삭제)한다.
        3) 저장 후 used_memory 가 maxmemory 를 넘으면 LRU 순으로 제거한다.
        """
        entry_size = utf8_len(key) + utf8_len(value)
        if self.maxmemory > 0 and entry_size > self.maxmemory:
            raise OutOfMemoryError()

        record = self._data.get(key)
        if record is not None:
            # 덮어쓰기: 메모리 회계는 값 차이만큼 조정, TTL은 규정대로 제거
            self.used_memory += utf8_len(value) - utf8_len(record.value)
            record.value = value
            self._expires.remove(key)          # 기존 TTL 초기화
            self._touch(key, record)           # 사용했으므로 LRU 갱신
        else:
            node = self._lru.insert_front(key)  # 최신 사용으로 등록
            self._data.put(key, Record(value, node))
            self.used_memory += entry_size

        return self._evict_until_within_limit()

    def get(self, key):
        """GET key -> 값 또는 None(nil)

        만료된 키는 먼저 삭제한 뒤 None 을 반환하며, 이때 LRU는 갱신하지 않는다.
        값을 실제로 반환하는 경우에만 LRU를 갱신한다.
        """
        if self._expire_if_needed(key):
            return None
        record = self._data.get(key)
        if record is None:
            return None
        self._touch(key, record)
        return record.value

    def delete(self, key):
        """DEL key -> 1 또는 0. 데이터/LRU/TTL에서 함께 제거한다."""
        self._expire_if_needed(key)
        return 1 if self._delete_key(key) else 0

    def exists(self, key):
        """EXISTS key -> 1 또는 0 (만료 확인 후 판단)."""
        self._expire_if_needed(key)
        return 1 if self._data.contains(key) else 0

    def dbsize(self):
        """DBSIZE -> 살아 있는 키 개수."""
        self.active_expire_cycle()
        return self._data.size()

    def keys(self):
        """KEYS -> 전체 키 목록(순서는 보장하지 않음)."""
        self.active_expire_cycle()
        result = []
        for key in self._data.keys():
            if not self._is_expired(key):
                result.append(key)
        return result

    # ===================================================================== 메모리
    def config_set_maxmemory(self, value):
        """CONFIG SET maxmemory bytes (0 = 무제한).

        설정 직후에도 초과 상태라면 즉시 LRU 제거를 수행한다.
        """
        self.maxmemory = value
        return self._evict_until_within_limit()

    def info_memory(self):
        """INFO memory 에 출력할 3개 지표."""
        self.active_expire_cycle()
        return (self.used_memory, self.maxmemory, self.evicted_keys)

    # ======================================================================= TTL
    def expire(self, key, seconds):
        """EXPIRE key seconds -> 1 또는 0

        - 없는 키: 0
        - seconds <= 0: 즉시 만료(존재하면 삭제 후 1)
        - 정상: 만료 시각을 기록하고 힙에 (expire_at, key) 를 push
        """
        if self._expire_if_needed(key) or not self._data.contains(key):
            return 0
        if seconds <= 0:
            self._delete_key(key)
            return 1
        expire_at = self._clock() + seconds
        self._expires.put(key, expire_at)
        self._ttl_heap.push((expire_at, key))
        return 1

    def ttl(self, key):
        """TTL key -> 남은 초 / -1(만료 없음) / -2(키 없음)."""
        if self._expire_if_needed(key) or not self._data.contains(key):
            return -2
        expire_at = self._expires.get(key)
        if expire_at is None:
            return -1
        remaining = expire_at - self._clock()
        if remaining <= 0:
            self._delete_key(key)
            self.expired_keys += 1
            return -2
        return int(remaining)

    # ============================================================== 관찰/디버그
    def lru_order(self):
        """최근 사용 순서대로 키 목록(front -> back). 테스트/설명용."""
        return list(self._lru)

    def ttl_heap_size(self):
        """힙에 남아 있는 항목 수(낡은 항목 포함). 테스트/설명용."""
        return self._ttl_heap.size()
