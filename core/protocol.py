"""Redis 스타일 응답 값과 출력 포맷.

엔진(store.py)은 아래 응답 객체만 만들고, 문자열로 그리는 일은 여기서 한다.
덕분에 테스트 코드는 문자열 대신 값 자체를 검사할 수 있다.
"""


class Reply(object):
    """모든 응답의 공통 부모."""

    def render(self):
        raise NotImplementedError


class SimpleString(Reply):
    """`OK` 처럼 그대로 출력되는 상태 문자열."""

    def __init__(self, text):
        self.text = text

    def render(self):
        return self.text


class Integer(Reply):
    """`(integer) 1` 형태의 정수 응답."""

    def __init__(self, value):
        self.value = value

    def render(self):
        return "(integer) %d" % self.value


class BulkString(Reply):
    """문자열 값 응답. value 가 None 이면 `(nil)`."""

    def __init__(self, value):
        self.value = value

    def render(self):
        if self.value is None:
            return "(nil)"
        return '"%s"' % self.value


class Array(Reply):
    """`1. "user:2"` 처럼 번호를 붙여 출력하는 배열 응답."""

    def __init__(self, values):
        self.values = values

    def render(self):
        if not self.values:
            return "(empty array)"
        lines = []
        for i, v in enumerate(self.values, start=1):
            lines.append('%d. "%s"' % (i, v))
        return "\n".join(lines)


class Raw(Reply):
    """INFO 처럼 여러 줄을 그대로 내보내는 응답."""

    def __init__(self, text):
        self.text = text

    def render(self):
        return self.text


class Error(Reply):
    """`(error) ...` 형태의 에러 응답."""

    def __init__(self, message):
        self.message = message

    def render(self):
        return "(error) %s" % self.message


# --------------------------------------------------------------- 표준 에러들
def unknown_command(name):
    return Error("ERR unknown command '%s'" % name)


def wrong_arity(name):
    return Error("ERR wrong number of arguments for '%s' command" % name)


def not_an_integer():
    return Error("ERR value is not an integer or out of range")


def oom():
    return Error("OOM command not allowed when used_memory > 'maxmemory'")


class OutOfMemoryError(Exception):
    """단일 엔트리가 maxmemory 보다 커서 저장 자체가 불가능할 때."""
