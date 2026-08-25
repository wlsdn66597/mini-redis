"""체이닝(chaining) 방식으로 직접 구현한 해시맵.

파이썬 내장 dict / set / collections 를 쓰지 않고,
"고정 길이 배열(list) + 각 버킷마다 이중 연결 리스트" 조합으로 만들었다.

- 배열은 인덱스 접근(O(1))만 사용하고, 키-값 저장 자체는 직접 구현한다.
- 버킷 내부 충돌은 DoublyLinkedList 로 이어 붙인다(체이닝).
- 로드 팩터가 0.75 를 넘으면 버킷 개수를 2배로 늘리고 전부 재배치한다.
"""

from structures.linked_list import DoublyLinkedList

INITIAL_CAPACITY = 8      # 시작 버킷 개수 (2의 거듭제곱)
MAX_LOAD_FACTOR = 0.75    # 이 값을 넘으면 버킷을 2배로 확장


class Entry:
    """버킷 체인에 실제로 담기는 키-값 쌍."""

    __slots__ = ("key", "value")

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return "Entry(%r, %r)" % (self.key, self.value)


class HashMap:
    """직접 구현한 체이닝 해시맵. 평균 O(1)의 put/get/remove 를 제공한다."""

    def __init__(self, capacity=INITIAL_CAPACITY):
        self._capacity = capacity
        # 고정 길이 배열: 각 칸은 그 버킷의 체인(이중 연결 리스트)
        self._buckets = [DoublyLinkedList() for _ in range(capacity)]
        self._size = 0

    # ------------------------------------------------------------- 해시 함수
    def _hash(self, key):
        """직접 설계한 문자열 해시 함수 (FNV-1a 계열 변형).

        입력: 임의의 파이썬 값(문자열이 아니면 str() 로 바꿔 사용)
        과정:
          1) 키를 UTF-8 바이트열로 만든다  -> 한글/영문/숫자를 동일하게 처리
          2) 32비트 offset basis 에서 시작해
             바이트마다 XOR 후 소수(prime)를 곱한다
          3) 매 단계 0xFFFFFFFF 마스크로 32비트를 유지한다
        출력: 32비트 정수 해시값

        XOR 로 바이트값을 섞고 소수를 곱해 비트를 상위로 퍼뜨리기 때문에
        "user:1", "user:2" 처럼 한 글자만 다른 키도 전혀 다른 값이 된다.
        """
        if not isinstance(key, str):
            key = str(key)
        data = key.encode("utf-8")
        h = 2166136261                       # FNV-1a 32bit offset basis
        for byte in data:
            h ^= byte
            h = (h * 16777619) & 0xFFFFFFFF  # FNV prime, 32비트 유지
        return h

    def _index(self, key):
        """해시값을 버킷 개수 범위의 인덱스로 접는다.

        용량이 항상 2의 거듭제곱이므로 (h % capacity) 대신
        비트마스크 (h & (capacity - 1)) 를 써서 나눗셈을 피한다.
        """
        return self._hash(key) & (self._capacity - 1)

    # ------------------------------------------------------------ 기본 연산
    def put(self, key, value):
        """키를 저장하거나 갱신한다. 평균 O(1)

        같은 키가 이미 체인에 있으면 값만 덮어쓰고 크기는 늘리지 않는다.
        새 키라면 체인 앞에 붙이고(최근 삽입일수록 빨리 찾힘) 크기를 늘린 뒤,
        로드 팩터를 확인해 필요하면 확장한다.
        """
        bucket = self._buckets[self._index(key)]
        for node in bucket.iter_nodes():
            if node.data.key == key:
                node.data.value = value
                return False                 # 신규 삽입 아님
        bucket.insert_front(Entry(key, value))
        self._size += 1
        if self._size > self._capacity * MAX_LOAD_FACTOR:
            self._resize(self._capacity * 2)
        return True                          # 신규 삽입

    def get(self, key, default=None):
        """키에 대응하는 값을 반환한다. 없으면 default. 평균 O(1)"""
        bucket = self._buckets[self._index(key)]
        for node in bucket.iter_nodes():
            if node.data.key == key:
                return node.data.value
        return default

    def remove(self, key):
        """키를 제거하고 (제거됨?, 값) 을 반환한다. 평균 O(1)"""
        bucket = self._buckets[self._index(key)]
        for node in bucket.iter_nodes():
            if node.data.key == key:
                value = node.data.value
                bucket.remove_node(node)     # 노드 참조를 알고 있으므로 O(1)
                self._size -= 1
                return True, value
        return False, None

    def contains(self, key):
        """키 존재 여부. 평균 O(1)"""
        bucket = self._buckets[self._index(key)]
        for node in bucket.iter_nodes():
            if node.data.key == key:
                return True
        return False

    def keys(self):
        """모든 키를 리스트로 모아 반환한다. O(n + capacity)"""
        result = []
        for bucket in self._buckets:
            for entry in bucket:
                result.append(entry.key)
        return result

    def items(self):
        """모든 (키, 값) 쌍을 리스트로 반환한다. O(n + capacity)"""
        result = []
        for bucket in self._buckets:
            for entry in bucket:
                result.append((entry.key, entry.value))
        return result

    def size(self):
        """저장된 키 개수. O(1)"""
        return self._size

    def capacity(self):
        """현재 버킷 개수. O(1)"""
        return self._capacity

    def load_factor(self):
        """현재 로드 팩터 = 키 개수 / 버킷 개수."""
        return self._size / float(self._capacity)

    def clear(self):
        """전체 비우기."""
        self._capacity = INITIAL_CAPACITY
        self._buckets = [DoublyLinkedList() for _ in range(self._capacity)]
        self._size = 0

    def __len__(self):
        return self._size

    def __contains__(self, key):
        return self.contains(key)

    # ------------------------------------------------------------------ 확장
    def _resize(self, new_capacity):
        """버킷 배열을 new_capacity 로 키우고 모든 엔트리를 재배치한다. O(n)

        절차:
          1) 기존 버킷 배열을 따로 들고 있는다.
          2) 새 용량으로 빈 버킷 배열을 만든다.
          3) 기존 엔트리를 하나씩 꺼내 '새 용량 기준으로 인덱스를 다시 계산'해
             새 버킷의 앞에 붙인다. (해시값 자체는 그대로지만 마스크가 달라져
             엔트리가 두 갈래로 재분배된다.)
        확장 비용은 O(n)이지만 삽입 n회당 한 번 정도라 분할상환 O(1)이다.
        """
        old_buckets = self._buckets
        self._capacity = new_capacity
        self._buckets = [DoublyLinkedList() for _ in range(new_capacity)]
        for bucket in old_buckets:
            for entry in bucket:
                idx = self._index(entry.key)
                self._buckets[idx].insert_front(entry)
