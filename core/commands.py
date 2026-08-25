"""명령어 파싱과 디스패치.

입력 한 줄 -> 토큰 분해 -> 명령 실행 -> Reply 객체 반환.
CLI(main.py)는 반환된 Reply 의 render() 결과만 출력하면 된다.
"""

from core import protocol
from core.protocol import (Array, BulkString, Error, Integer, OutOfMemoryError,
                           Raw, SimpleString)


class ParseError(Exception):
    """따옴표가 닫히지 않는 등 토큰 분해 자체가 실패한 경우."""


def tokenize(line):
    """입력 줄을 토큰 리스트로 나눈다.

    규칙(과제 최소 요구를 만족하는 단순 규칙):
      - 공백으로 구분한다.
      - 큰따옴표로 감싸면 내부 공백을 포함한 하나의 토큰이 된다.
      - 큰따옴표 안에서는 \\" 와 \\\\ 이스케이프를 인정한다.

    예) SET user:1 "Alice Kim"  ->  ['SET', 'user:1', 'Alice Kim']
    """
    tokens = []
    buf = []
    in_quotes = False
    escaped = False
    has_token = False

    for ch in line:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if in_quotes:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_quotes = False
            else:
                buf.append(ch)
            continue
        if ch == '"':
            in_quotes = True
            has_token = True
        elif ch.isspace():
            if has_token or buf:
                tokens.append("".join(buf))
                buf = []
                has_token = False
        else:
            buf.append(ch)
            has_token = True

    if in_quotes or escaped:
        raise ParseError("unbalanced quotes in request")
    if has_token or buf:
        tokens.append("".join(buf))
    return tokens


def parse_int(text):
    """정수 파싱. 실패하면 None 을 돌려주고 호출부가 표준 에러를 낸다."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


class CommandHandler:
    """MiniRedis 엔진 위에 얹히는 명령 실행기."""

    def __init__(self, engine):
        self.engine = engine

    def execute_line(self, line):
        """입력 한 줄을 실행하고 Reply 를 반환한다. 빈 줄이면 None."""
        try:
            tokens = tokenize(line)
        except ParseError:
            return Error("ERR Protocol error: unbalanced quotes in request")
        if not tokens:
            return None
        return self.execute(tokens)

    def execute(self, tokens):
        """토큰 배열을 실행한다."""
        raw_name = tokens[0]
        name = raw_name.upper()
        args = tokens[1:]

        # 만료 예정 키를 먼저 정리한다(힙 루트 확인은 O(1)).
        self.engine.active_expire_cycle()

        if name == "SET":
            return self._set(args)
        if name == "GET":
            return self._get(args)
        if name == "DEL":
            return self._del(args)
        if name == "EXISTS":
            return self._exists(args)
        if name == "DBSIZE":
            return self._dbsize(args)
        if name == "KEYS":
            return self._keys(args)
        if name == "CONFIG":
            return self._config(args)
        if name == "INFO":
            return self._info(args)
        if name == "EXPIRE":
            return self._expire(args)
        if name == "TTL":
            return self._ttl(args)
        if name == "HELP":
            return Raw(HELP_TEXT)
        return protocol.unknown_command(raw_name)

    # --------------------------------------------------------------- String
    def _set(self, args):
        if len(args) != 2:
            return protocol.wrong_arity("SET")
        try:
            self.engine.set(args[0], args[1])
        except OutOfMemoryError:
            return protocol.oom()
        return SimpleString("OK")

    def _get(self, args):
        if len(args) != 1:
            return protocol.wrong_arity("GET")
        return BulkString(self.engine.get(args[0]))

    def _del(self, args):
        if len(args) != 1:
            return protocol.wrong_arity("DEL")
        return Integer(self.engine.delete(args[0]))

    def _exists(self, args):
        if len(args) != 1:
            return protocol.wrong_arity("EXISTS")
        return Integer(self.engine.exists(args[0]))

    def _dbsize(self, args):
        if args:
            return protocol.wrong_arity("DBSIZE")
        return Integer(self.engine.dbsize())

    def _keys(self, args):
        # 패턴 매칭은 구현 범위가 아니므로 '*' 만 관용적으로 받아준다.
        if len(args) > 1 or (len(args) == 1 and args[0] != "*"):
            return protocol.wrong_arity("KEYS")
        return Array(self.engine.keys())

    # --------------------------------------------------------------- 메모리
    def _config(self, args):
        if len(args) != 3 or args[0].upper() != "SET":
            return protocol.wrong_arity("CONFIG")
        param = args[1].lower()
        if param != "maxmemory":
            return Error("ERR Unknown CONFIG parameter '%s'" % args[1])
        value = parse_int(args[2])
        if value is None or value < 0:
            return protocol.not_an_integer()
        self.engine.config_set_maxmemory(value)
        return SimpleString("OK")

    def _info(self, args):
        if len(args) > 1:
            return protocol.wrong_arity("INFO")
        section = args[0].lower() if args else "memory"
        if section != "memory":
            return Error("ERR Unsupported INFO section '%s'" % args[0])
        used, maxmem, evicted = self.engine.info_memory()
        return Raw("used_memory:%d\nmaxmemory:%d\nevicted_keys:%d"
                   % (used, maxmem, evicted))

    # ------------------------------------------------------------------ TTL
    def _expire(self, args):
        if len(args) != 2:
            return protocol.wrong_arity("EXPIRE")
        seconds = parse_int(args[1])
        if seconds is None:
            return protocol.not_an_integer()
        return Integer(self.engine.expire(args[0], seconds))

    def _ttl(self, args):
        if len(args) != 1:
            return protocol.wrong_arity("TTL")
        return Integer(self.engine.ttl(args[0]))


HELP_TEXT = """지원 명령어
  SET key value              값 저장 (LRU 갱신, 덮어쓰기 시 TTL 초기화)
  GET key                    값 조회 (성공 시에만 LRU 갱신)
  DEL key                    키 삭제 (데이터/LRU/TTL 동시 제거)
  EXISTS key                 존재 여부
  DBSIZE                     키 개수
  KEYS                       전체 키 목록
  CONFIG SET maxmemory N     메모리 상한(바이트, 0=무제한)
  INFO memory                used_memory / maxmemory / evicted_keys
  EXPIRE key seconds         만료 시간 설정
  TTL key                    남은 만료 시간 (-1: 없음, -2: 키 없음)
  HELP                       이 도움말
  exit | quit                종료"""
