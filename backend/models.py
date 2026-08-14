from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GameVersion(Base):
    __tablename__ = "game_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch: Mapped[str] = mapped_column(String(16), unique=True)
    season: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime)


class Spec(Base):
    __tablename__ = "specs"
    __table_args__ = (UniqueConstraint("version_id", "class_key", "spec_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.id", ondelete="CASCADE"))
    class_key: Mapped[str] = mapped_column(String(40))
    spec_key: Mapped[str] = mapped_column(String(40))
    class_name_zh_cn: Mapped[str] = mapped_column(String(40))
    spec_name_zh_cn: Mapped[str] = mapped_column(String(40))
    role: Mapped[str | None] = mapped_column(String(16))
    mastery_coefficient: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    rules_json: Mapped[dict | None] = mapped_column(JSON)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("version_id", "game_item_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.id", ondelete="CASCADE"))
    game_item_id: Mapped[int] = mapped_column(BigInteger)
    name_en: Mapped[str | None] = mapped_column(String(255))
    name_zh_cn: Mapped[str | None] = mapped_column(String(255))
    slot_key: Mapped[str] = mapped_column(String(32))
    armor_type: Mapped[str | None] = mapped_column(String(20))
    weapon_type: Mapped[str | None] = mapped_column(String(32))
    icon: Mapped[str | None] = mapped_column(String(255))
    max_sockets: Mapped[int] = mapped_column(Integer, default=0)
    is_crafted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tier: Mapped[bool] = mapped_column(Boolean, default=False)
    has_special_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class ItemVariant(Base):
    __tablename__ = "item_variants"
    __table_args__ = (UniqueConstraint("item_id", "item_level"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    upgrade_track: Mapped[str | None] = mapped_column(String(20))
    upgrade_rank: Mapped[int | None] = mapped_column(Integer)
    item_level: Mapped[int] = mapped_column(Integer)
    strength: Mapped[int] = mapped_column(Integer, default=0)
    agility: Mapped[int] = mapped_column(Integer, default=0)
    intellect: Mapped[int] = mapped_column(Integer, default=0)
    stamina: Mapped[int] = mapped_column(Integer, default=0)
    critical_strike: Mapped[int] = mapped_column(Integer, default=0)
    haste: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[int] = mapped_column(Integer, default=0)
    versatility: Mapped[int] = mapped_column(Integer, default=0)
    sockets: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class ItemSource(Base):
    __tablename__ = "item_sources"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(32))
    instance_name_en: Mapped[str | None] = mapped_column(String(255))
    instance_name_zh_cn: Mapped[str | None] = mapped_column(String(255))
    encounter_name_en: Mapped[str | None] = mapped_column(String(255))
    encounter_name_zh_cn: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1024))


class StatRecommendation(Base):
    __tablename__ = "stat_recommendations"
    __table_args__ = (UniqueConstraint("spec_id", "content_type", "target_type"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id", ondelete="CASCADE"))
    content_type: Mapped[str] = mapped_column(String(24))
    target_type: Mapped[str] = mapped_column(String(24))
    values_json: Mapped[dict] = mapped_column(JSON)
    is_recommended_spec: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_note: Mapped[str | None] = mapped_column(Text)


class BisProfile(Base):
    __tablename__ = "bis_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("specs.id", ondelete="CASCADE"))
    content_type: Mapped[str] = mapped_column(String(24), default="overall")
    source_url: Mapped[str] = mapped_column(String(1024))
    source_updated: Mapped[str | None] = mapped_column(String(32))
    variant_index: Mapped[int] = mapped_column(Integer, default=1)


class BisItem(Base):
    __tablename__ = "bis_items"
    __table_args__ = (UniqueConstraint("profile_id", "slot_key", "position"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("bis_profiles.id", ondelete="CASCADE"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    slot_key: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=1)
    source_text: Mapped[str | None] = mapped_column(String(255))


class User(Timestamps, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Character(Timestamps, Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("user_id", "name", "realm", "region"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    realm: Mapped[str] = mapped_column(String(96), default="")
    region: Mapped[str] = mapped_column(String(8), default="cn")
    class_key: Mapped[str] = mapped_column(String(40))
    spec_key: Mapped[str] = mapped_column(String(40))
    simc_text: Mapped[str | None] = mapped_column(Text)
    current_item_level: Mapped[int | None] = mapped_column(Integer)


class Loadout(Timestamps, Base):
    __tablename__ = "loadouts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    creator_name: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    class_key: Mapped[str | None] = mapped_column(String(40))
    spec_key: Mapped[str | None] = mapped_column(String(40))
    patch: Mapped[str] = mapped_column(String(16))
    content_type: Mapped[str] = mapped_column(String(24))
    target_type: Mapped[str] = mapped_column(String(24))
    target_stats_json: Mapped[dict] = mapped_column(JSON)
    constraints_json: Mapped[dict | None] = mapped_column(JSON)
    calculated_stats_json: Mapped[dict | None] = mapped_column(JSON)
    state_json: Mapped[dict | None] = mapped_column(JSON)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)


class LoadoutItem(Base):
    __tablename__ = "loadout_items"
    __table_args__ = (UniqueConstraint("loadout_id", "slot_key"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    loadout_id: Mapped[int] = mapped_column(ForeignKey("loadouts.id", ondelete="CASCADE"))
    slot_key: Mapped[str] = mapped_column(String(32))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"))
    catalyst_tier_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    item_level: Mapped[int] = mapped_column(Integer)
    upgrade_track: Mapped[str | None] = mapped_column(String(20))
    upgrade_rank: Mapped[int | None] = mapped_column(Integer)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    max_sockets_snapshot: Mapped[int] = mapped_column(Integer, default=0)


class LoadoutGem(Base):
    __tablename__ = "loadout_gems"
    __table_args__ = (UniqueConstraint("loadout_item_id", "socket_index"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    loadout_item_id: Mapped[int] = mapped_column(ForeignKey("loadout_items.id", ondelete="CASCADE"))
    socket_index: Mapped[int] = mapped_column(Integer)
    gem_item_id: Mapped[int] = mapped_column(BigInteger)


class LoadoutConsumable(Base):
    __tablename__ = "loadout_consumables"
    __table_args__ = (UniqueConstraint("loadout_id", "consumable_type"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    loadout_id: Mapped[int] = mapped_column(ForeignKey("loadouts.id", ondelete="CASCADE"))
    consumable_type: Mapped[str] = mapped_column(String(32))
    item_id: Mapped[int] = mapped_column(BigInteger)


class ChatSession(Timestamps, Base):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    loadout_id: Mapped[int | None] = mapped_column(ForeignKey("loadouts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(96))
    tool_result_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
