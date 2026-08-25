# Mini Redis

파이썬 내장 `dict` / `set` / `collections` 를 **전혀 쓰지 않고**,
해시맵 · 이중 연결 리스트 · 최소 힙을 밑바닥부터 구현해 만든 CLI 기반 In-Memory Key-Value 저장소입니다.

Redis 가 왜 빠른지를 "말로 설명"하는 대신, **LRU 자동 제거**와 **TTL 만료**가
어떤 자료구조 조합으로 O(1) / O(log n) 이 되는지를 코드로 직접 확인하는 것이 목표입니다.

```
mini-redis> CONFIG SET maxmemory 30
OK
mini-redis> SET user:1 "Alice"
OK
mini-redis> SET user:2 "Bob"
OK
mini-redis> SET user:3 "Charlie"
OK
mini-redis> GET user:1
(nil)                      <- maxmemory(30) 초과로 LRU(user:1)가 자동 제거됨
mini-redis> INFO memory
used_memory:22
maxmemory:30
evicted_keys:1
```

---

## 1. 실행 방법

```bash
python main.py
```

```bash
python main.py --demo
```

```bash
python -m unittest discover -s tests -t . -v
```

* 개발 환경: **Python 3.8 이상** (외부 라이브러리 없음, 표준 라이브러리는 `time`/`sys` 만 사용)
* `--demo` 는 과제 예시 시나리오(LRU 제거 → INFO → TTL 만료 → 에러 4종)를 그대로 재생합니다.
* 테스트는 **56개**가 모두 통과합니다.

---

## 2. 프로젝트 구조

```
mini-redis/
├── main.py                     REPL(mini-redis> 프롬프트) + --demo 시나리오
├── structures/                 ★ 직접 구현한 자료구조 (독립 모듈)
│   ├── linked_list.py            이중 연결 리스트 (LRU + 해시맵 체이닝에 재사용)
│   ├── hash_map.py               체이닝 해시맵 (직접 설계한 해시 함수 + 2배 확장)
│   └── heap.py                   최소 힙 (TTL 만료 시각 관리)
├── core/
│   ├── store.py                  MiniRedis 엔진 (자료구조 3종을 조립)
│   ├── commands.py               토크나이저 + 명령 디스패치
│   └── protocol.py               Redis 스타일 응답/에러 포맷
└── tests/
    └── test_mini_redis.py      평가 항목 1~4에 대응하는 테스트 56개
```

---

## 3. 지원 명령어

| 분류 | 명령어 | 동작 | 출력 |
|---|---|---|---|
| String | `SET key value` | 값 저장. 성공 시 LRU 갱신, 덮어쓰기면 **TTL 초기화** | `OK` |
| String | `GET key` | 값 조회. **반환에 성공한 경우에만** LRU 갱신 | `"value"` / `(nil)` |
| String | `DEL key` | 데이터·LRU·TTL 구조에서 **동시 제거** | `(integer) 1` / `(integer) 0` |
| String | `EXISTS key` | 존재 여부(만료 확인 후 판단) | `(integer) 1` / `(integer) 0` |
| String | `DBSIZE` | 살아 있는 키 개수 | `(integer) N` |
| String | `KEYS` | 전체 키 목록(패턴 매칭 미구현) | `1. "user:2"` / `(empty array)` |
| 메모리 | `CONFIG SET maxmemory N` | 메모리 상한(바이트). `0` = 무제한 | `OK` |
| 메모리 | `INFO memory` | `used_memory` / `maxmemory` / `evicted_keys` | 3줄 출력 |
| TTL | `EXPIRE key seconds` | 만료 시간 설정(0 이하 = 즉시 만료) | `(integer) 1` / `(integer) 0` |
| TTL | `TTL key` | 남은 초 | `N` / `-1`(만료 없음) / `-2`(키 없음) |
| CLI | `HELP`, `exit`, `quit` | 도움말 / 종료 | — |

**값 파싱**: 공백 없는 값과 `"큰따옴표로 감싼 값"` 을 모두 지원하며,
따옴표 안에서는 `\"` 와 `\\` 이스케이프가 동작합니다. (`SET name "Alice Kim"` → 하나의 값)

---

## 4. 평가 항목별 설명

### 항목 1 — 기능 동작

| 체크 항목 | 어디서 확인되는가 |
|---|---|
| String 기본 6개 명령 정상 동작 | `python main.py --demo`, `TestStringCommands` (9개) |
| maxmemory 초과 시 가장 오래된 키 자동 제거 | `TestLruEviction.test_assignment_example_scenario` — 과제 예시 그대로 재현 |
| `INFO memory` 규격 출력 | `TestInfoMemory` — `used_memory:22 / maxmemory:30 / evicted_keys:1` |
| EXPIRE·TTL 동작 및 만료 키 제거 | `TestTtl` (11개) — 가짜 시계(FakeClock)로 시간 경과를 결정론적으로 검증 |
| 에러 표준 형식 출력 | `TestErrorHandling` (8개) — 아래 4종 전부 |

에러 출력 표준:

```
(error) ERR unknown command 'HELLO'
(error) ERR wrong number of arguments for 'GET' command
(error) ERR value is not an integer or out of range
(error) OOM command not allowed when used_memory > 'maxmemory'
```

---

### 항목 2 — 자료구조를 어떻게 구성했는가

#### 2-1. 이중 연결 리스트 — 노드 구조와 O(1)의 근거

[`structures/linked_list.py`](structures/linked_list.py)

```python
class Node:
    __slots__ = ("prev", "next", "data")   # prev / next / data 세 필드
```

리스트는 `head`, `tail`, `_size` 세 가지 상태만 유지합니다.

| 메서드 | 하는 일 | O(1)인 이유 |
|---|---|---|
| `insert_front` / `insert_back` | 양 끝에 노드 추가 | `head`/`tail` 포인터를 직접 들고 있어 끝을 찾을 필요가 없음 |
| `remove_front` / `remove_back` | 양 끝 노드 제거 | 위와 동일 |
| `remove_node(node)` | **참조로 받은** 노드 제거 | 탐색 단계가 아예 없음. `node.prev.next`, `node.next.prev` 두 링크만 갈아끼움 |
| `move_to_front(node)` | 노드를 맨 앞으로 이동 | "떼어내기 + 앞에 붙이기" 둘 다 포인터 조작. **새 노드를 만들지 않아** 할당 비용도 없음 |

핵심은 `remove_node` 가 **노드 참조를 인자로 받는다**는 설계입니다.
일반적인 연결 리스트라면 "값으로 노드를 찾는 데 O(n)"이 들지만,
Mini Redis 는 해시맵이 `키 → 노드 참조`를 알려주므로 탐색 단계가 사라집니다.
이 한 가지가 LRU 전체를 O(1)로 만듭니다.

`__iter__` 는 순회 중 삭제가 일어나도 안전하도록 다음 노드를 **미리 확보**한 뒤 `yield` 합니다.

#### 2-2. 해시맵 — 해시 함수는 어떤 과정을 거치는가

[`structures/hash_map.py`](structures/hash_map.py)

직접 설계한 해시 함수는 **FNV-1a 32비트** 계열입니다.

```python
def _hash(self, key):
    data = key.encode("utf-8")           # 1) 입력: 문자열 -> UTF-8 바이트열
    h = 2166136261                       # 2) 32비트 offset basis에서 시작
    for byte in data:
        h ^= byte                        # 3) 바이트를 XOR로 섞고
        h = (h * 16777619) & 0xFFFFFFFF  # 4) 소수(FNV prime)를 곱해 상위 비트로 확산
    return h                             # 5) 출력: 32비트 정수
```

* **입력**: 임의의 키(문자열이 아니면 `str()` 로 변환) → UTF-8 바이트열이므로 한글 키도 동일하게 처리됩니다.
* **과정**: XOR 로 바이트 값을 주입하고, 소수를 곱해 하위 비트의 변화가 상위 비트까지 퍼지게 만듭니다(avalanche).
  덕분에 `user:1` 과 `user:2` 처럼 한 글자만 다른 키도 완전히 다른 해시값을 갖습니다.
* **인덱스 생성**: 버킷 개수를 항상 2의 거듭제곱으로 유지하므로
  `h % capacity` 대신 **비트마스크** `h & (capacity - 1)` 를 씁니다(나눗셈 제거).

분포 품질은 테스트로 확인합니다 — 키 1000개를 넣었을 때
사용된 버킷 수가 이상적 기대치 `m·(1 − e^(−n/m))` 의 90% 이상이고,
가장 긴 체인이 8 미만임을 검증합니다 (`test_hash_is_deterministic_and_spread`).

#### 2-3. 충돌 해결 — 체이닝 (버킷 내부 구조 선택)

```
_buckets  [0]───▶ DoublyLinkedList: Entry("user:3","Charlie") ⇄ Entry("k9", ...)
          [1]───▶ (비어 있음)
          [2]───▶ DoublyLinkedList: Entry("user:2","Bob")
          ...
```

* 버킷 배열은 **고정 길이 배열(인덱스 접근 전용)** 로만 사용하고,
  실제 키-값 저장은 각 버킷의 **이중 연결 리스트**가 담당합니다.
  → 2-1에서 만든 자료구조를 그대로 재사용(과제 권장 사항)했습니다.
* 버킷 안에는 `Entry(key, value)` 객체가 들어갑니다. 해시 충돌이 나도 `key` 를 다시 비교하므로 값이 섞이지 않습니다.
* **왜 이중 연결 리스트인가**: `remove()` 가 체인에서 노드를 뗄 때
  단일 연결 리스트라면 "이전 노드"를 따로 추적해야 하지만,
  이중 연결 리스트는 `node.prev` 가 있어 `remove_node(node)` 한 번으로 끝납니다.
* 새 키는 체인의 **앞**에 붙입니다(최근에 넣은 키를 더 빨리 찾게 됨).
* `test_chaining_on_forced_collision` 은 버킷 수를 1로 강제해 모든 키를 한 체인에 몰아넣고도
  `get` 이 정확히 동작하는지 확인합니다.

#### 2-4. 로드 팩터 0.75 초과 시 "버킷 2배 확장" 절차

```python
if self._size > self._capacity * MAX_LOAD_FACTOR:   # 0.75
    self._resize(self._capacity * 2)
```

확장 절차는 다음 3단계입니다 (`_resize`).

1. **기존 버킷 배열을 따로 보관**한다.
2. `capacity` 를 2배로 올리고, 그 크기의 **빈 버킷 배열을 새로 만든다**.
3. 기존 엔트리를 하나씩 꺼내 **새 용량 기준으로 인덱스를 다시 계산**해 새 버킷 앞에 붙인다.
   해시값 자체는 변하지 않지만 마스크가 `capacity-1` 로 넓어지므로,
   기존 한 버킷의 엔트리들이 `i` 와 `i + old_capacity` 두 갈래로 재분배됩니다.

확장 1회 비용은 O(n)이지만 삽입이 n번 쌓여야 한 번 일어나므로 **분할상환 O(1)** 입니다.
확장을 하는 이유는 명확합니다 — 로드 팩터가 커지면 체인이 길어지고,
평균 탐색 비용이 O(1)에서 O(체인 길이)로 무너지기 때문입니다.
(`test_resize_doubles_capacity`, `test_data_survives_resize` 로 검증)

#### 2-5. 최소 힙

[`structures/heap.py`](structures/heap.py) — 완전 이진 트리를 배열로 표현합니다.
인덱스 `i` 의 부모는 `(i-1)//2`, 자식은 `2i+1` / `2i+2` 입니다.

* `push` : 맨 뒤에 붙이고 `_heapify_up` 으로 부모보다 작으면 계속 위로 → O(log n)
* `pop`  : 루트를 꺼내고 마지막 원소를 루트에 올린 뒤 `_heapify_down` → O(log n)
* `peek` : 루트를 그대로 반환 → **O(1)**

원소는 `(expire_at, key)` 튜플이며, 튜플 비교가 첫 원소인 만료 시각을 먼저 보므로
"가장 먼저 만료될 키"가 항상 루트에 유지됩니다.

---

### 항목 3 — 동작 원리

#### 3-1. LRU에서 "해시맵 + 이중 연결 리스트"가 각각 맡는 역할

| 자료구조 | 역할 | 혼자서는 왜 부족한가 |
|---|---|---|
| **해시맵** | 키 → 값 **조회**를 O(1)로 | 순서 정보가 없어 "누가 가장 오래됐는지" 알 수 없음 |
| **이중 연결 리스트** | 최근 사용 **순서 유지** (front=최신, back=최고참) | 특정 키의 노드를 찾으려면 O(n) 탐색이 필요 |

두 구조를 잇는 접착제가 `core/store.py` 의 `Record` 입니다.

```python
class Record:
    __slots__ = ("value", "lru_node")   # 값 + '그 키의 LRU 노드 참조'
```

해시맵이 값과 **함께 노드 참조를 돌려주기 때문에**, 리스트 탐색이 완전히 사라집니다.
그래서 둘 다 필요합니다 — 해시맵은 *어디에 있는지*, 리스트는 *언제 쓰였는지*를 담당합니다.

```
HashMap                          DoublyLinkedList (LRU)
 "user:3" ─▶ Record(Charlie, ●)──▶ [user:3] ⇄ [user:2] ⇄ [user:1]
 "user:2" ─▶ Record(Bob,     ●)──────┘  ▲                     ▲
 "user:1" ─▶ Record(Alice,   ●)─────────┘             front=최신  back=가장 오래됨(제거 대상)
```

#### 3-2. O(1) LRU = "조회(해시) + 갱신(리스트 이동)"

한 번의 `GET` 이 하는 일을 비용으로 쪼개면 이렇습니다.

1. **조회** — `HashMap.get(key)` : 해시 계산 O(1) + 짧은 체인 비교 O(1) → `Record` 획득
2. **갱신** — `DoublyLinkedList.move_to_front(record.lru_node)` : 링크 4개 재연결 → O(1)

즉 *찾는 비용*은 해시맵이, *순서를 바꾸는 비용*은 리스트가 각각 상수로 처리합니다.
제거할 때도 마찬가지로 `_lru.tail` 이 곧 LRU 대상이므로 **선택 자체가 O(1)** 입니다.
(`test_get_refreshes_lru_order`, `test_recently_used_key_survives_eviction` 참고)

#### 3-3. TTL 관리에 힙을 쓰는 이유

만료 관리에서 반복적으로 필요한 질문은 하나입니다 — **"지금 만료된 키가 있는가?"**

* 전수 검사: 모든 키의 만료 시각을 확인 → 명령마다 **O(n)**
* 최소 힙: 루트만 보면 됨 → `peek()` **O(1)**, 실제 제거는 `pop()` O(log n)

힙은 "최솟값(= 가장 이른 만료)을 항상 루트에 유지"하는 성질을 가지므로,
루트의 시각이 아직 미래라면 **나머지는 볼 필요조차 없다**고 즉시 단정할 수 있습니다.
이것이 정렬 배열(삽입 O(n))이나 리스트(탐색 O(n)) 대신 힙을 쓰는 이유입니다.

구현은 **lazy deletion** 전략을 씁니다. `EXPIRE` 로 TTL 이 갱신되면 힙에는 낡은
`(expire_at, key)` 가 남지만, 꺼낼 때 `_expires` 의 현재 값과 **일치할 때만** 실제로 삭제합니다.

```python
expire_at, key = self._ttl_heap.pop()
current = self._expires.get(key)
if current is None or current != expire_at:
    continue                 # 이미 지워졌거나 TTL이 바뀐 낡은 항목 -> 무시
self._delete_key(key)
```

만료 처리는 두 경로로 일어납니다.

* **lazy** (`_expire_if_needed`) — 키 기반 명령이 실행되기 직전, 해당 키만 확인
* **active** (`active_expire_cycle`) — 매 명령 시작 시 힙 루트부터 만료된 것들을 걷어냄

#### 3-4. 메모리 초과 시 eviction 흐름 (단계별)

`used_memory = Σ( len(utf8(key)) + len(utf8(value)) )` — 규정대로 노드/포인터/버킷 오버헤드는 제외합니다.

`SET user:3 "Charlie"` (maxmemory=30, 현재 20B) 한 줄이 실행되는 과정:

| 단계 | 처리 | 상태 변화 |
|---|---|---|
| ① | `entry_size = utf8(key)+utf8(value)` = 6+7 = **13** 계산 | — |
| ② | `entry_size > maxmemory` 인지 확인 → 아니면 통과 (맞으면 **저장하지 않고 OOM 에러**) | — |
| ③ | 기존 키면 값 차이만큼만 가감 + **TTL 초기화**, 새 키면 LRU 앞에 노드 삽입 후 해시맵에 저장 | `used_memory 20 → 33` |
| ④ | `maxmemory > 0 and used_memory > maxmemory` 검사 | 33 > 30 → eviction 진입 |
| ⑤ | `self._lru.tail.data` = **`user:1`** (가장 오래 사용되지 않은 키) 선택 — O(1) | — |
| ⑥ | `_delete_key` 로 해시맵·LRU 리스트·TTL 맵에서 **동시 제거**하고 `used_memory` 차감 | `33 → 22` |
| ⑦ | `evicted_keys += 1` | `evicted_keys = 1` |
| ⑧ | ④로 돌아가 조건이 풀릴 때까지 반복 | 22 ≤ 30 → 종료 |

한 번의 `SET` 으로 여러 키가 제거될 수 있습니다 (`test_multiple_evictions_in_one_set`).
② 단계 덕분에 **방금 저장한 키가 자기 자신 때문에 쫓겨나는 일은 발생하지 않습니다.**
`CONFIG SET maxmemory` 로 상한을 낮출 때도 같은 루프가 즉시 돌아갑니다.

#### 3-5. `GET key` 전체 흐름

```
GET user:2
  │
  ├─ ① active_expire_cycle()      힙 루트 확인 O(1) — 만료된 키들 정리
  │
  ├─ ② _expire_if_needed(key)     이 키가 만료됐는가?
  │       └─ YES ─▶ 데이터/LRU/TTL에서 삭제 ─▶ (nil) 반환  ※ LRU 갱신 안 함
  │
  ├─ ③ _data.get(key)             해시맵 조회 O(1)
  │       └─ None ─▶ (nil) 반환                      ※ LRU 갱신 안 함
  │
  ├─ ④ _touch(key, record)        move_to_front(record.lru_node) — O(1) LRU 갱신
  │                               ※ '반환에 성공한 경우에만' 갱신하는 것이 규정
  │
  └─ ⑤ "Bob" 반환
```

즉 **TTL 확인 → 삭제 여부 판단 → 값 반환 → (성공 시에만) LRU 갱신** 순서입니다.
만료로 삭제된 경우 LRU 를 건드리지 않는다는 점을 `test_expired_get_does_not_refresh_lru` 로 못 박아 두었습니다.

#### 3-6. 명시된 엣지 케이스

| 규칙 | 구현 위치 | 테스트 |
|---|---|---|
| 만료된 키는 GET 시 먼저 삭제 후 `(nil)`, LRU 갱신 없음 | `store.get` | `test_expired_get_does_not_refresh_lru` |
| SET 덮어쓰기 시 TTL 초기화 | `store.set` 의 `self._expires.remove(key)` | `test_set_overwrite_clears_ttl` |
| 없는 키에 EXPIRE → `(integer) 0` | `store.expire` | `test_expire_missing_key_is_zero` |
| DEL 은 데이터/TTL/LRU 를 함께 제거 | `store._delete_key` | `test_del_removes_ttl_entry_too` |
| 단일 엔트리가 maxmemory 초과 → 저장 안 하고 OOM | `store.set` 의 `OutOfMemoryError` | `test_single_entry_larger_than_maxmemory_is_oom` |
| `maxmemory 0` = 무제한 | `_evict_until_within_limit` 의 `maxmemory > 0` 조건 | `test_maxmemory_zero_is_unlimited` |

---

### 항목 4 — 확장 질문

#### 4-1. "LRU 대신 LFU 정책을 구현한다면 자료구조를 어떻게 바꿔야 하는가?"

LFU 는 기준이 **최근성(recency)** 에서 **빈도(frequency)** 로 바뀝니다.
단순히 "리스트 맨 앞으로 이동"으로는 표현할 수 없고, 접근 횟수 카운터가 필요합니다.

가장 단순한 안(빈도 최소 힙)은 문제가 있습니다 — 접근할 때마다 카운터가 오르면
힙 안의 위치를 갱신해야 하는데, 임의 원소의 위치를 알기 위해
`키 → 힙 인덱스` 맵을 별도로 유지하고 `_heapify_up/_down` 을 호출해야 하므로
**GET 한 번이 O(log n)** 이 됩니다. 지금의 O(1)이 깨집니다.

그래서 O(1)을 유지하려면 **빈도 버킷(frequency bucket) 구조**를 씁니다.

```
freq_list:  [freq=1] ⇄ [freq=2] ⇄ [freq=5] ...        (빈도 자체도 이중 연결 리스트)
               │           │           │
               ▼           ▼           ▼
           키 리스트    키 리스트    키 리스트         (각 빈도 안에서는 LRU 순서)
```

* 지금 코드에서 **재사용 가능한 것**: `HashMap`(키 → 노드 참조), `DoublyLinkedList`(노드 O(1) 이동/삭제).
* **바뀌는 것**: LRU 리스트 하나가 "빈도 노드들의 리스트 + 각 빈도가 소유한 키 리스트"의 2단 구조가 되고,
  `Record` 에 `freq` 와 `freq_node` 필드가 추가됩니다.
* `GET` 시: 현재 빈도 노드에서 키를 떼어(O(1)) 다음 빈도 노드로 옮깁니다.
  다음 빈도 노드가 없으면 새로 만들어 끼워 넣습니다 — 모두 O(1).
* 제거 시: **가장 낮은 빈도 노드의 꼬리 키**를 버립니다. `freq_list.head` 가 최소 빈도이므로 O(1).
* 같은 빈도 안에서는 LRU 로 tie-break 하므로, **LFU 는 LRU 를 버리는 게 아니라 한 겹 위에 얹는 구조**입니다.
* 추가 고려: 오래전에 폭발적으로 조회된 키가 영원히 남는 *cache pollution* 문제.
  실제 Redis 는 8비트 로그 카운터 + 시간에 따른 감쇠(decay)로 완화합니다.

#### 4-2. "데이터가 10만 건으로 늘어나면 병목은 어디이고, 어떻게 개선하는가?"

현재 구조는 10만 건에서도 **자료구조 자체는 O(1)을 유지**합니다
(`test_10k_keys_stay_consistent` 로 1만 건 일관성 검증). 병목은 다른 곳에 있습니다.

| # | 병목 지점 | 원인 | 개선 방향 |
|---|---|---|---|
| 1 | **`KEYS` 명령** | 전체 버킷 순회 + 만료 확인 → O(n + capacity). 10만 건이면 한 번에 수십 ms 정지 | Redis 처럼 `SCAN` 커서 방식으로 나눠 반환. 실제 Redis 도 프로덕션에서 `KEYS` 사용을 권장하지 않음 |
| 2 | **`_resize` 순간 지연** | 로드 팩터 초과 시 전체 재해싱 O(n). 분할상환은 O(1)이지만 **그 한 번의 SET 이 튄다**(tail latency) | Redis 의 **incremental rehashing**: 새 테이블을 함께 두고 명령마다 버킷 몇 개씩만 옮김 |
| 3 | **TTL 힙의 낡은 항목 누적** | lazy deletion 이라 EXPIRE 를 반복 갱신하면 힙에 죽은 항목이 쌓여 메모리·`pop` 비용 증가 | 낡은 항목 비율이 임계치를 넘으면 힙 재구축, 또는 `키 → 힙 인덱스` 맵으로 즉시 교체 |
| 4 | **해시 함수 호출 비용** | 파이썬 레벨에서 바이트 단위 루프 → 키가 길수록 선형 비용 | 긴 키는 앞뒤 일부 + 길이만 해싱, 또는 `Record` 에 해시값 캐시(재해싱 때 재계산 불필요) |
| 5 | **대량 eviction 스파이크** | maxmemory 를 크게 낮추면 한 번에 수만 건 제거 | 한 명령당 제거 개수 상한을 두고 나머지는 다음 명령으로 이월 |
| 6 | **파이썬 객체 오버헤드** | 키 10만 개면 `Node` + `Entry` + `Record` = 30만 객체. 실제 RSS 는 `used_memory` 의 수십 배 | 4-3 참고. 근본 개선은 값 인코딩 압축(Redis 의 `embstr`/`ziplist` 계열) |

우선순위는 **1 → 2 → 3** 입니다. 1, 2번이 사용자가 체감하는 지연을 직접 만듭니다.

#### 4-3. "`used_memory` 에 자료구조 오버헤드까지 포함하는 모델로 바꾸면?"

**무엇이 달라지는가**

* 현재 모델은 `키+값 바이트`만 셉니다. 실제로는 키 하나당
  `Node`(prev/next/data) + `Entry`(key/value) + `Record`(value/lru_node) +
  버킷 배열 슬롯 + TTL 맵 엔트리가 함께 존재합니다.
  CPython 기준 짧은 키 하나가 **수백 바이트**를 쓰므로, 오버헤드를 포함하면 `used_memory` 는 **한 자릿수 배수 이상 커집니다.**
* 그 결과 **같은 maxmemory 에서 저장 가능한 키 수가 급감**하고, `evicted_keys` 가 훨씬 빨리 늘어납니다.
* 값의 크기와 무관한 **키당 고정 비용**이 생기므로, "작은 값을 많이" 넣는 워크로드가
  "큰 값을 조금" 넣는 워크로드보다 불리해집니다. 즉 **eviction 순서가 아니라 eviction 빈도의 성격이 바뀝니다.**
* 버킷 배열은 키 하나에 귀속되지 않는 **공유 비용**이라, "이 키의 메모리"를 정의하는 일 자체가 애매해집니다.
  게다가 `_resize` 가 일어나는 순간 아무 키도 추가되지 않았는데 `used_memory` 가 계단식으로 뜁니다.
* 단일 엔트리 OOM 판정 기준도 달라집니다 — 값이 작아도 오버헤드 때문에 저장이 거부될 수 있습니다.

**공정한 비교/채점을 위해 필요한 보정**

1. **오버헤드 모델을 상수로 명문화**한다.
   `sys.getsizeof` 는 인터프리터·버전·플랫폼마다 값이 달라 채점 재현성이 깨지므로,
   `NODE_OVERHEAD = 48`, `ENTRY_OVERHEAD = 32` 처럼 **고정 상수**를 규정에 박아두고 계산합니다.
2. **공유 비용과 엔트리 비용을 분리해 보고**한다.
   `INFO memory` 에 `used_memory`(엔트리 합계)와 `overhead_memory`(버킷 배열 등)를 나누어 출력하고,
   eviction 판정은 둘의 합으로 하되 채점은 `used_memory` 기준으로 하면 두 모델을 함께 볼 수 있습니다.
   (실제 Redis 도 `used_memory` / `used_memory_dataset` / `used_memory_overhead` 를 구분합니다.)
3. **maxmemory 기준값을 재조정**한다. 같은 `maxmemory 30` 이라도 새 모델에서는 키 한 개도 못 넣습니다.
   테스트 시나리오의 상한을 오버헤드 배수만큼 함께 올리지 않으면 기존 테스트가 전부 OOM 으로 무너집니다.
4. **`_resize` 시점의 계단 상승을 어떻게 다룰지 정한다.** 버킷 확장이 곧바로 eviction 을 유발하지 않도록,
   확장 비용은 `overhead_memory` 에만 반영하고 eviction 트리거에서는 제외하는 편이 예측 가능성이 높습니다.

---

## 5. 제약 사항 준수

| 제약 | 준수 방법 |
|---|---|
| `dict`, `set`, `collections` 사용 금지 | 소스 전체에서 미사용. 키-값 저장은 `HashMap`, 순서는 `DoublyLinkedList`, 우선순위는 `MinHeap` 이 담당 |
| 고정 길이 배열은 인덱스 접근 수준으로만 | `HashMap._buckets` 만 파이썬 `list` 이며 **인덱스 접근 전용**. `MinHeap._items` 도 완전 이진 트리의 배열 표현 |
| 자료구조는 독립 모듈로 분리 | `structures/linked_list.py`, `structures/hash_map.py`, `structures/heap.py` |
| 핵심 클래스/함수에 주석 또는 docstring | 모든 공개 클래스·메서드에 docstring, 복잡도와 설계 의도 명시 |
| 네트워크 통신 미구현 | CLI(REPL) 전용 |
| 데이터 영속성 미구현 | 메모리에만 저장 |
| List/Set/Sorted Set 미구현 | String 타입만 지원 |
| 동시성 처리 불요 | 단일 스레드 REPL |

확인용:

```bash
grep -rnE "\b(dict|set|collections)\(" --include=*.py structures core main.py
```

---

## 6. 테스트

```
Ran 56 tests in 0.25s

OK
```

| 테스트 클래스 | 개수 | 대응 항목 |
|---|---|---|
| `TestDoublyLinkedList` | 5 | 항목 2 — 노드 구조, O(1) 삽입/삭제/이동 |
| `TestHashMap` | 6 | 항목 2 — 해시 함수 분포, 체이닝, 로드 팩터 확장 |
| `TestMinHeap` | 4 | 항목 2·3 — `(expire_at, key)` 처리 |
| `TestStringCommands` | 9 | 항목 1 — String 기본 6개 명령 |
| `TestLruEviction` | 8 | 항목 1·3 — 과제 예시 재현, LRU 순서, OOM |
| `TestInfoMemory` | 2 | 항목 1 — INFO 규격 |
| `TestTtl` | 11 | 항목 1·3 — 만료 및 엣지 케이스 (가짜 시계 사용) |
| `TestErrorHandling` | 8 | 항목 1 — 에러 표준 4종, 토크나이저 |
| `TestScaleAndConsistency` | 3 | 항목 4 — 1만 건 규모에서 메모리 회계·구조 동기화 |

TTL 테스트는 `FakeClock` 을 주입해 **실제로 기다리지 않고** 시간을 앞당기므로
테스트 전체가 0.3초 안에 끝나면서도 만료 동작을 결정론적으로 검증합니다.
