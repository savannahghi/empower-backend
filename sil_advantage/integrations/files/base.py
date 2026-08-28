"""Abstract file classes."""
from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Optional, Self


class AbstractFile(ABC):
    """Abstract File."""

    def __init__(
        self,
        name: str,
        size: int,
        mime_type: str,
        created: Any = None,
        modified: Any = None,
        metadata: Optional[dict] = None,
        adapter: Any = None,
    ) -> None:
        """Initialize the file."""
        self.name = name
        self.mime_type = mime_type
        self.size = size
        self.created = created
        self.modified = modified
        self.metadata = metadata
        self.adapter = adapter

    @abstractproperty
    def hash(self) -> str:
        """Calculate the file hash."""

    @abstractmethod
    def read(self) -> bytes:
        """Read the file."""

    @abstractmethod
    def move(self, dest: str) -> None:
        """Move the file to destination `dest`."""

    @abstractproperty
    def parent(self) -> Optional[Self]:
        """Return the parent folder of the current file/folder."""
