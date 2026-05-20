"""
base.py — 모든 커넥터가 구현해야 할 추상 인터페이스.
1소스 = 1파일 원칙 (CLAUDE.md 아키텍처).
외부 API 응답은 반드시 connector에서 Event로 정규화 후 반환한다.
"""
from abc import ABC, abstractmethod

from models.event import Event


class BaseConnector(ABC):
    @abstractmethod
    async def fetch(self) -> list[Event]:
        """데이터 소스에서 이벤트를 가져와 Event 리스트로 반환한다."""
        ...
