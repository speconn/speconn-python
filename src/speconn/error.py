from __future__ import annotations


class Code:
    __slots__ = ("_name", "_http_status")
    _BY_NAME: dict[str, Code] = {}

    def __init__(self, name: str, http_status: int) -> None:
        self._name = name
        self._http_status = http_status
        Code._BY_NAME[name] = self

    def as_str(self) -> str:
        return self._name

    def http_status(self) -> int:
        return self._http_status

    @classmethod
    def from_str(cls, name: str) -> Code:
        return cls._BY_NAME.get(name, Code.UNKNOWN)

    @classmethod
    def from_http_status(cls, status: int) -> Code:
        _MAP: dict[int, Code] = {
            400: cls.INTERNAL,
            401: cls.UNAUTHENTICATED,
            403: cls.PERMISSION_DENIED,
            404: cls.UNIMPLEMENTED,
            429: cls.UNAVAILABLE,
            502: cls.UNAVAILABLE,
            503: cls.UNAVAILABLE,
            504: cls.UNAVAILABLE,
        }
        return _MAP.get(status, cls.UNKNOWN)

    def __repr__(self) -> str:
        return f"Code({self._name!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Code):
            return self._name == other._name
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._name)


Code.CANCELED = Code("canceled", 499)
Code.UNKNOWN = Code("unknown", 500)
Code.INVALID_ARGUMENT = Code("invalid_argument", 400)
Code.DEADLINE_EXCEEDED = Code("deadline_exceeded", 504)
Code.NOT_FOUND = Code("not_found", 404)
Code.ALREADY_EXISTS = Code("already_exists", 409)
Code.PERMISSION_DENIED = Code("permission_denied", 403)
Code.RESOURCE_EXHAUSTED = Code("resource_exhausted", 429)
Code.FAILED_PRECONDITION = Code("failed_precondition", 400)
Code.ABORTED = Code("aborted", 409)
Code.OUT_OF_RANGE = Code("out_of_range", 400)
Code.UNIMPLEMENTED = Code("unimplemented", 501)
Code.INTERNAL = Code("internal", 500)
Code.UNAVAILABLE = Code("unavailable", 503)
Code.DATA_LOSS = Code("data_loss", 500)
Code.UNAUTHENTICATED = Code("unauthenticated", 401)


CODE_TO_STATUS: dict[str, int] = {
    c.as_str(): c.http_status()
    for c in (
        Code.CANCELED,
        Code.UNKNOWN,
        Code.INVALID_ARGUMENT,
        Code.DEADLINE_EXCEEDED,
        Code.NOT_FOUND,
        Code.ALREADY_EXISTS,
        Code.PERMISSION_DENIED,
        Code.RESOURCE_EXHAUSTED,
        Code.FAILED_PRECONDITION,
        Code.ABORTED,
        Code.OUT_OF_RANGE,
        Code.UNIMPLEMENTED,
        Code.INTERNAL,
        Code.UNAVAILABLE,
        Code.DATA_LOSS,
        Code.UNAUTHENTICATED,
    )
}


class SpeconnError(Exception):
    def __init__(self, code: Code, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.as_str()}: {message}")
