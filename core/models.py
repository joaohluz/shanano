from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    fingerprints: Mapped[list["Fingerprint"]] = relationship(
        "Fingerprint", back_populates="song", cascade="all, delete-orphan"
    )


class Fingerprint(Base):
    __tablename__ = "fingerprints"

    hash: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    song_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    anchor_time: Mapped[int] = mapped_column(Integer, nullable=False)
    anchor_freq: Mapped[int] = mapped_column(Integer, nullable=False)
    target_time: Mapped[int] = mapped_column(Integer, nullable=False)
    target_freq: Mapped[int] = mapped_column(Integer, nullable=False)

    song: Mapped["Song"] = relationship("Song", back_populates="fingerprints")
