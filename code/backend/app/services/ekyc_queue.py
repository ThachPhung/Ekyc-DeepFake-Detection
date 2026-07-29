import json
import socket
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from app.core.config import settings


class EkycQueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class RedisConnectionInfo:
    host: str
    port: int
    db: int
    password: str | None
    username: str | None
    use_tls: bool


def _parse_redis_url(redis_url: str) -> RedisConnectionInfo:
    parsed = urlparse(redis_url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise EkycQueueError("REDIS_URL must use redis:// or rediss://")

    db = 0
    if parsed.path and parsed.path != "/":
        try:
            db = int(parsed.path.lstrip("/"))
        except ValueError as exc:
            raise EkycQueueError("REDIS_URL database must be a number") from exc

    return RedisConnectionInfo(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        db=db,
        password=unquote(parsed.password) if parsed.password else None,
        username=unquote(parsed.username) if parsed.username else None,
        use_tls=parsed.scheme == "rediss",
    )


def _encode_command(*parts: str) -> bytes:
    encoded_parts = [part.encode("utf-8") for part in parts]
    chunks = [f"*{len(encoded_parts)}\r\n".encode("ascii")]
    for part in encoded_parts:
        chunks.append(f"${len(part)}\r\n".encode("ascii"))
        chunks.append(part)
        chunks.append(b"\r\n")
    return b"".join(chunks)


def _read_line(sock_file: Any) -> bytes:
    line = sock_file.readline()
    if not line:
        raise EkycQueueError("Redis connection closed unexpectedly")
    return line.rstrip(b"\r\n")


def _read_response(sock_file: Any) -> Any:
    prefix = sock_file.read(1)
    if not prefix:
        raise EkycQueueError("Redis connection closed unexpectedly")

    if prefix == b"+":
        return _read_line(sock_file).decode("utf-8")
    if prefix == b"-":
        raise EkycQueueError(_read_line(sock_file).decode("utf-8"))
    if prefix == b":":
        return int(_read_line(sock_file))
    if prefix == b"$":
        length = int(_read_line(sock_file))
        if length == -1:
            return None
        data = sock_file.read(length)
        sock_file.read(2)
        return data.decode("utf-8")
    if prefix == b"*":
        length = int(_read_line(sock_file))
        return [_read_response(sock_file) for _ in range(length)]

    raise EkycQueueError(f"Unsupported Redis response prefix: {prefix!r}")


def _execute_redis_command(
    connection: RedisConnectionInfo,
    *parts: str,
    timeout: float = 5.0,
) -> Any:
    raw_sock = socket.create_connection((connection.host, connection.port), timeout=timeout)
    sock: socket.socket | ssl.SSLSocket = raw_sock
    if connection.use_tls:
        sock = ssl.create_default_context().wrap_socket(
            raw_sock,
            server_hostname=connection.host,
        )

    try:
        sock_file = sock.makefile("rb")
        if connection.password:
            auth_parts = (
                ("AUTH", connection.username, connection.password)
                if connection.username
                else ("AUTH", connection.password)
            )
            sock.sendall(_encode_command(*auth_parts))
            _read_response(sock_file)
        if connection.db:
            sock.sendall(_encode_command("SELECT", str(connection.db)))
            _read_response(sock_file)

        sock.sendall(_encode_command(*parts))
        return _read_response(sock_file)
    finally:
        sock.close()


def enqueue_ekyc_job(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    connection = _parse_redis_url(settings.REDIS_URL)
    _execute_redis_command(connection, "RPUSH", settings.EKYC_QUEUE_NAME, serialized)


def enqueue_ekyc_ocr_job(payload: dict[str, Any]) -> None:
    enqueue_ekyc_job(payload)


def ping_redis() -> bool:
    connection = _parse_redis_url(settings.REDIS_URL)
    response = _execute_redis_command(connection, "PING", timeout=2.0)
    return response == "PONG"


def get_ekyc_queue_length() -> int:
    connection = _parse_redis_url(settings.REDIS_URL)
    response = _execute_redis_command(
        connection,
        "LLEN",
        settings.EKYC_QUEUE_NAME,
        timeout=2.0,
    )
    if not isinstance(response, int):
        raise EkycQueueError("Redis LLEN returned an unexpected response")
    return response
