from __future__ import annotations

from dataclasses import dataclass

from ieim.broker.broker import Broker, BrokerMessage


@dataclass(frozen=True)
class RabbitMQConfig:
    amqp_url: str
    prefetch_count: int = 10
    dead_letter_exchange: str = "ieim.dlx"
    dead_letter_suffix: str = "__dlq"
    max_attempts: int = 5


@dataclass(frozen=True)
class _InFlight:
    delivery_tag: int
    queue: str
    body: bytes
    attempts: int


class RabbitMQBroker(Broker):
    def __init__(self, *, config: RabbitMQConfig) -> None:
        if not config.amqp_url:
            raise ValueError("amqp_url must be non-empty")
        if config.prefetch_count <= 0:
            raise ValueError("prefetch_count must be > 0")
        if config.max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        self._config = config

        self._connection = None
        self._channel = None
        self._inflight: dict[str, _InFlight] = {}

    def _require_pika(self):
        try:
            import pika  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("pika is required for RabbitMQBroker (requirements/runtime.txt)") from e
        return pika

    def _ensure_connected(self) -> None:
        if self._connection is not None and self._channel is not None:
            return

        pika = self._require_pika()
        params = pika.URLParameters(self._config.amqp_url)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.basic_qos(prefetch_count=int(self._config.prefetch_count))
        self._channel.exchange_declare(exchange=self._config.dead_letter_exchange, exchange_type="direct", durable=True)

    def _declare_queue(self, *, queue: str) -> None:
        self._ensure_connected()
        assert self._channel is not None

        dlq = queue + self._config.dead_letter_suffix
        self._channel.queue_declare(queue=dlq, durable=True)
        self._channel.queue_bind(queue=dlq, exchange=self._config.dead_letter_exchange, routing_key=dlq)

        args = {
            "x-dead-letter-exchange": self._config.dead_letter_exchange,
            "x-dead-letter-routing-key": dlq,
        }
        self._channel.queue_declare(queue=queue, durable=True, arguments=args)

    def publish(self, *, queue: str, body: bytes) -> None:
        if not queue:
            raise ValueError("queue must be a non-empty string")
        if not isinstance(body, (bytes, bytearray)):
            raise ValueError("body must be bytes")

        self._declare_queue(queue=queue)
        assert self._channel is not None

        pika = self._require_pika()
        props = pika.BasicProperties(
            delivery_mode=2,
            headers={"x-ieim-attempt": 0},
        )
        self._channel.basic_publish(exchange="", routing_key=queue, body=bytes(body), properties=props, mandatory=False)

    def consume(self, *, queue: str, max_messages: int = 1) -> list[BrokerMessage]:
        if not queue:
            raise ValueError("queue must be a non-empty string")
        if max_messages <= 0:
            return []

        self._declare_queue(queue=queue)
        assert self._channel is not None

        out: list[BrokerMessage] = []
        for _ in range(int(max_messages)):
            method_frame, properties, body = self._channel.basic_get(queue=queue, auto_ack=False)
            if method_frame is None:
                break

            headers = getattr(properties, "headers", None)
            attempts = 0
            if isinstance(headers, dict):
                v = headers.get("x-ieim-attempt")
                if isinstance(v, int):
                    attempts = v

            delivery_id = f"{queue}:{method_frame.delivery_tag}"
            self._inflight[delivery_id] = _InFlight(
                delivery_tag=int(method_frame.delivery_tag),
                queue=queue,
                body=bytes(body or b""),
                attempts=int(attempts),
            )
            out.append(
                BrokerMessage(
                    delivery_id=delivery_id,
                    queue=queue,
                    body=bytes(body or b""),
                    attempts=int(attempts),
                )
            )

        return out

    def ack(self, *, delivery_id: str) -> None:
        inflight = self._inflight.pop(delivery_id, None)
        if inflight is None:
            raise ValueError("delivery_id is not in-flight")

        self._ensure_connected()
        assert self._channel is not None
        self._channel.basic_ack(delivery_tag=inflight.delivery_tag)

    def nack(self, *, delivery_id: str, requeue: bool) -> None:
        inflight = self._inflight.pop(delivery_id, None)
        if inflight is None:
            raise ValueError("delivery_id is not in-flight")

        self._ensure_connected()
        assert self._channel is not None

        if requeue:
            next_attempt = int(inflight.attempts) + 1
            if next_attempt >= int(self._config.max_attempts):
                dlq = inflight.queue + self._config.dead_letter_suffix
                self._channel.basic_publish(
                    exchange=self._config.dead_letter_exchange,
                    routing_key=dlq,
                    body=inflight.body,
                    properties=self._require_pika().BasicProperties(
                        delivery_mode=2,
                        headers={"x-ieim-attempt": next_attempt},
                    ),
                )
                self._channel.basic_ack(delivery_tag=inflight.delivery_tag)
                return

            self._channel.basic_publish(
                exchange="",
                routing_key=inflight.queue,
                body=inflight.body,
                properties=self._require_pika().BasicProperties(
                    delivery_mode=2,
                    headers={"x-ieim-attempt": next_attempt},
                ),
            )
            self._channel.basic_ack(delivery_tag=inflight.delivery_tag)
            return

        self._channel.basic_nack(delivery_tag=inflight.delivery_tag, requeue=False)
