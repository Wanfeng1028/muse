"""Pydantic contract for cues.json (see scripts/cues.schema.md). Accepts camelCase or snake_case keys."""
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=to_camel)


class Segment(Strict):
    source_start: float = Field(ge=0)
    source_end: float

    @model_validator(mode="after")
    def check_order(self) -> "Segment":
        if self.source_end <= self.source_start:
            raise ValueError(f"segment end {self.source_end} must be after start {self.source_start}")
        return self


class Music(Strict):
    file: str
    segments: list[Segment] | None = None
    edit: dict[str, Segment] | None = Field(default=None, description="Legacy {a: seg, b: seg}; joined in key order.")
    at: float = Field(default=0.0, description="Film time where the (edited) music starts; negative trims its head.")
    gain_db: float = 0.0
    fade_in: float = Field(default=0.0, ge=0)
    tempo: float = Field(default=1.0, ge=0.5, le=2.0, description="Pitch-preserving stretch (atempo); keep within 0.92-1.08.")
    beats: str | None = Field(default=None, description="Optional beats.json from music_analyze.py to check cuts sit on bars.")

    @model_validator(mode="after")
    def merge_edit(self) -> "Music":
        if self.segments and self.edit:
            raise ValueError("music: give either segments or edit, not both")
        if self.edit:
            self.segments = [self.edit[name] for name in sorted(self.edit)]
        return self


class Clip(Strict):
    file: str
    at: float = Field(description="Film time of the clip start (or of its peak when align='peak').")
    gain_db: float = 0.0
    source_start: float = Field(default=0.0, ge=0)
    source_end: float | None = None
    align: Literal["start", "peak"] = "start"
    id: str | None = None


class Sfx(Strict):
    kind: str | None = Field(default=None, description="foley.py kind (synthesized).")
    file: str | None = None
    at: float = Field(description="Film time where the transient (peak) lands, or the file start when align='start'.")
    gain: float = Field(default=1.0, ge=0, description="Linear gain on top of --sfx-peak-db (0.3-0.6 for most events, up to 1 for hero hits).")
    gain_db: float = 0.0
    note: float | None = Field(default=None, description="Semitones above the key's tonic (pitched kinds).")
    length: float | None = Field(default=None, gt=0, description="Seconds for whoosh/swell/riser/shimmer/reverse-swoosh.")
    variant: int = Field(default=0, ge=0, description="Different noise for repeated sounds.")
    align: Literal["peak", "start"] = "peak"
    role: Literal["event", "texture"] = Field(
        default="event",
        description="'texture' for runs meant to sit under the bed (tick runs, typing keys); events must be heard.",
    )

    @model_validator(mode="after")
    def one_source(self) -> "Sfx":
        if (self.kind is None) == (self.file is None):
            raise ValueError("each sfx cue needs exactly one of kind or file")
        return self


class Cues(Strict):
    duration: float = Field(gt=0, description="Film length in seconds; the mix is exactly this long.")
    key: str | None = Field(default=None, description="Music key for pitched foley, e.g. 'F' or 'A minor'.")
    music: Music | None = None
    vo: list[Clip] = Field(default_factory=list)
    product: list[Clip] = Field(default_factory=list, validation_alias=AliasChoices("product", "cards", "diegetic"))
    sfx: list[Sfx] = Field(default_factory=list)
    voice: str | None = None
    name: str | None = None
    fps: float | None = None
    meta: dict[str, object] | None = None
