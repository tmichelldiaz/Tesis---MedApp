from dataclasses import dataclass, field


@dataclass
class Unit:
    title: str | None
    level: int | None
    text: str
    pages: list[int] = field(default_factory=list)


@dataclass
class Segmentation:
    level: int | None
    units: list[Unit]
    dropped_headers: list[str] = field(default_factory=list)
    merged_heading_blocks: int = 0


@dataclass
class Concept:
    filename: str
    title: str
    description: str
    pages: list[int]
    content: str


@dataclass
class ValidationResult:
    state: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)


@dataclass
class Bundle:
    files: dict[str, str]
    concepts: list[Concept]
    segmentation_level: int | None
    validation: ValidationResult
