from dataclasses import dataclass, field


@dataclass
class Vehicle:
    id: int
    pos: list[int]
    jobs: list[tuple] = field(default_factory=list)
    post: tuple | None = None
