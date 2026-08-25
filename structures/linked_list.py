"""이중 연결 리스트(Doubly Linked List).

Mini Redis 안에서 두 가지 목적으로 재사용된다.

1. LRU 추적: 리스트의 앞(front)은 "가장 최근에 사용된 키",
   뒤(back)는 "가장 오래 사용되지 않은 키"를 의미한다.
2. 해시맵의 충돌 해결(체이닝): 각 버킷이 이 리스트 하나를 갖는다.

모든 삽입/삭제/이동 연산은 노드 참조만 조작하므로 O(1)이다.
탐색(순회)만 O(n)이며, 그것도 해시맵 버킷 내부처럼 짧은 구간에서만 쓴다.
"""


class Node:
    """이중 연결 리스트의 노드. prev / next / data 세 필드를 갖는다."""

    __slots__ = ("prev", "next", "data")

    def __init__(self, data):
        self.prev = None
        self.next = None
        self.data = data

    def __repr__(self):
        return "Node(%r)" % (self.data,)


class DoublyLinkedList:
    """head/tail 포인터와 길이를 유지하는 이중 연결 리스트."""

    def __init__(self):
        self.head = None   # 가장 앞 노드 (LRU 관점에서 most recently used)
        self.tail = None   # 가장 뒤 노드 (LRU 관점에서 least recently used)
        self._size = 0

    # ------------------------------------------------------------------ 조회
    def size(self):
        """저장된 노드 개수. O(1)"""
        return self._size

    def is_empty(self):
        """비어 있는지 여부. O(1)"""
        return self._size == 0

    def __len__(self):
        return self._size

    def __iter__(self):
        """앞에서 뒤로 순회하며 각 노드의 data를 넘겨준다. O(n)"""
        cur = self.head
        while cur is not None:
            nxt = cur.next          # 순회 중 삭제되어도 안전하도록 미리 확보
            yield cur.data
            cur = nxt

    def iter_nodes(self):
        """data가 아니라 노드 자체를 순회한다(해시맵 버킷 탐색용). O(n)"""
        cur = self.head
        while cur is not None:
            nxt = cur.next
            yield cur
            cur = nxt

    # ------------------------------------------------------------------ 삽입
    def insert_front(self, data):
        """맨 앞에 새 노드를 넣고 그 노드를 반환한다. O(1)"""
        node = Node(data)
        self._link_front(node)
        return node

    def insert_back(self, data):
        """맨 뒤에 새 노드를 넣고 그 노드를 반환한다. O(1)"""
        node = Node(data)
        if self.tail is None:
            self.head = node
            self.tail = node
        else:
            node.prev = self.tail
            self.tail.next = node
            self.tail = node
        self._size += 1
        return node

    # ------------------------------------------------------------------ 삭제
    def remove_front(self):
        """맨 앞 노드를 떼어내고 data를 반환한다. 비어 있으면 None. O(1)"""
        if self.head is None:
            return None
        node = self.head
        self.remove_node(node)
        return node.data

    def remove_back(self):
        """맨 뒤 노드를 떼어내고 data를 반환한다. 비어 있으면 None. O(1)

        LRU 제거(eviction)에서 "가장 오래 사용되지 않은 키"를 뽑는 연산이다.
        """
        if self.tail is None:
            return None
        node = self.tail
        self.remove_node(node)
        return node.data

    def remove_node(self, node):
        """이미 참조를 알고 있는 노드를 O(1)에 제거한다.

        탐색이 필요 없기 때문에 O(1)이며, LRU가 O(1)로 동작하는 핵심이다.
        (해시맵이 '키 -> 노드 참조'를 알려주므로 탐색 단계가 사라진다.)
        """
        if node is None:
            return None
        if node.prev is not None:
            node.prev.next = node.next
        else:
            self.head = node.next
        if node.next is not None:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
        node.prev = None
        node.next = None
        self._size -= 1
        return node.data

    # ------------------------------------------------------------------ 이동
    def move_to_front(self, node):
        """기존 노드를 맨 앞으로 옮긴다(= 방금 사용됨 표시). O(1)

        새 노드를 만들지 않고 링크만 갈아끼우므로 할당 비용도 없다.
        """
        if node is None or node is self.head:
            return node
        # 1) 현재 위치에서 떼어낸 뒤 2) 앞에 다시 붙인다.
        if node.prev is not None:
            node.prev.next = node.next
        if node.next is not None:
            node.next.prev = node.prev
        else:
            self.tail = node.prev
        node.prev = None
        node.next = None
        self._size -= 1
        self._link_front(node)
        return node

    # ------------------------------------------------------------------ 내부
    def _link_front(self, node):
        """이미 만들어진 노드를 맨 앞에 연결한다. O(1)"""
        node.prev = None
        node.next = self.head
        if self.head is not None:
            self.head.prev = node
        self.head = node
        if self.tail is None:
            self.tail = node
        self._size += 1
