"""배열 기반 최소 힙(Min-Heap).

Mini Redis 에서는 TTL 만료 관리에 쓴다.
원소는 (expire_at, key) 튜플이며, 튜플 비교가 첫 번째 원소인
만료 시각을 먼저 비교하므로 "가장 먼저 만료될 키"가 항상 루트에 온다.

- peek(): O(1)  -> 지금 만료된 게 있는지 한 번에 확인
- push(): O(log n)
- pop():  O(log n)

전수 검사(모든 키의 TTL을 매번 확인, O(n))를 O(1) 확인 + O(log n) 제거로
줄여주는 것이 힙을 쓰는 이유다.
"""


class MinHeap:
    """(expire_at, key) 같은 비교 가능한 원소를 담는 최소 힙."""

    def __init__(self):
        # 완전 이진 트리를 배열로 표현한다.
        # 인덱스 i 의 부모 = (i-1)//2, 자식 = 2i+1, 2i+2
        self._items = []

    # ------------------------------------------------------------ 기본 연산
    def push(self, item):
        """원소를 넣는다. O(log n)

        맨 뒤에 붙인 뒤 부모보다 작으면 계속 위로 올린다(_heapify_up).
        """
        self._items.append(item)
        self._heapify_up(len(self._items) - 1)

    def pop(self):
        """가장 작은 원소(= 가장 이른 만료)를 꺼낸다. 비면 None. O(log n)

        루트를 꺼내고 마지막 원소를 루트로 옮긴 뒤 아래로 내린다(_heapify_down).
        """
        if not self._items:
            return None
        top = self._items[0]
        last = self._items.pop()
        if self._items:
            self._items[0] = last
            self._heapify_down(0)
        return top

    def peek(self):
        """가장 작은 원소를 제거하지 않고 확인한다. 비면 None. O(1)"""
        if not self._items:
            return None
        return self._items[0]

    def size(self):
        """원소 개수. O(1)"""
        return len(self._items)

    def is_empty(self):
        return len(self._items) == 0

    def __len__(self):
        return len(self._items)

    # ------------------------------------------------------------------ 내부
    def _heapify_up(self, idx):
        """idx 원소를 부모와 비교하며 제자리를 찾을 때까지 올린다. O(log n)"""
        items = self._items
        while idx > 0:
            parent = (idx - 1) // 2
            if items[idx] < items[parent]:
                items[idx], items[parent] = items[parent], items[idx]
                idx = parent
            else:
                break

    def _heapify_down(self, idx):
        """idx 원소를 더 작은 자식과 바꿔가며 내린다. O(log n)"""
        items = self._items
        n = len(items)
        while True:
            left = 2 * idx + 1
            right = 2 * idx + 2
            smallest = idx
            if left < n and items[left] < items[smallest]:
                smallest = left
            if right < n and items[right] < items[smallest]:
                smallest = right
            if smallest == idx:
                break
            items[idx], items[smallest] = items[smallest], items[idx]
            idx = smallest
