from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import DatasetContent, TaxonomyNode
from app.services.dataset_contract import YOUTUBE_PUBLIC_DATASET_SOURCE


TAXONOMY_VERSION = "content-taxonomy-v1"
TAXONOMY_SOURCE = "project_defined"
MIN_VERIFIED_SAMPLES = 30
UNKNOWN_LEAF_KEY = "unknown"


@dataclass(frozen=True)
class TaxonomyNodeDefinition:
    key: str
    name: str
    name_th: str
    level: int
    parent_key: str | None = None
    is_leaf: bool = False
    is_trainable: bool = False
    profile_terms: tuple[str, ...] = ()
    collection_queries: tuple[str, ...] = ()
    minimum_sample_count: int = 0


def _leaf(
    key: str,
    name: str,
    name_th: str,
    parent_key: str,
    profile_terms: tuple[str, ...],
    collection_queries: tuple[str, ...],
) -> TaxonomyNodeDefinition:
    return TaxonomyNodeDefinition(
        key=key,
        name=name,
        name_th=name_th,
        level=3,
        parent_key=parent_key,
        is_leaf=True,
        is_trainable=True,
        profile_terms=profile_terms,
        collection_queries=collection_queries,
        minimum_sample_count=MIN_VERIFIED_SAMPLES,
    )


# This taxonomy belongs to the project. YouTube search queries only discover
# candidates; a human reviewer owns the final Level 3 label.
TAXONOMY_NODES: tuple[TaxonomyNodeDefinition, ...] = (
    TaxonomyNodeDefinition("technology", "Technology", "เทคโนโลยี", 1),
    TaxonomyNodeDefinition("electronics", "Electronics", "อุปกรณ์อิเล็กทรอนิกส์", 2, "technology"),
    _leaf(
        "phone",
        "Phone",
        "โทรศัพท์",
        "electronics",
        ("phone", "smartphone", "mobile", "มือถือ", "โทรศัพท์", "สมาร์ตโฟน"),
        (
            "รีวิวสมาร์ตโฟน หลังใช้งาน กล้อง แบตเตอรี่ -เคส -ซ่อม -ไมค์ -ไฟฉาย",
            "เปรียบเทียบมือถือ ประสิทธิภาพ กล้อง แบตเตอรี่ -เคส -ซ่อม",
            "รีวิว iPhone หลังใช้งาน แบตเตอรี่ กล้อง -เคส -ซ่อม",
            "รีวิวมือถือรุ่นใหม่ กล้อง แบตเตอรี่ ประสิทธิภาพ ข้อดีข้อเสีย -เคส -ซ่อม",
            "ทดสอบมือถือ เล่นเกม กล้อง แบตเตอรี่ หน้าจอ -เคส -ซ่อม",
            "มือถือเรือธง รีวิวหลังใช้งาน กล้อง แบตเตอรี่ ความร้อน -เคส -ซ่อม",
            "รีวิวมือถือ Android ใช้งานจริง กล้อง แบตเตอรี่ หน้าจอ -เคส -ซ่อม -ฟิล์ม",
            "รีวิวโทรศัพท์มือถือ ข้อดี ข้อเสีย สเปก ราคา -เคส -ซ่อม -อุปกรณ์เสริม",
            "มือถือรุ่นไหนดี รีวิว เปรียบเทียบ กล้อง แบตเตอรี่ -เคส -ซ่อม",
            "รีวิวมือถือราคาประหยัด งบ 5000 กล้อง แบตเตอรี่ -เคส -ซ่อม",
            "รีวิวมือถือระดับกลาง ใช้งานจริง กล้อง เกม แบตเตอรี่ -เคส -ซ่อม",
            "ทดสอบมือถือเล่นเกม เฟรมเรต ความร้อน แบตเตอรี่ -พัดลม -เคส",
            "ทดสอบกล้องมือถือ ถ่ายรูปกลางคืน วิดีโอ กันสั่น -เลนส์เสริม -ขาตั้ง",
            "แกะกล่องมือถือ รีวิวเครื่องจริง สเปก หน้าจอ กล้อง -เคส -ฟิล์ม",
            "รีวิวมือถือหลังใช้ 7 วัน ประสบการณ์ แบตเตอรี่ กล้อง -เคส -ซ่อม",
            "รีวิวมือถือหลังใช้ 1 เดือน ปัญหา ข้อดี ข้อเสีย -เคส -ซ่อม",
            "เปรียบเทียบ iPhone Android กล้อง แบตเตอรี่ ประสิทธิภาพ -เคส -ซ่อม",
            "รีวิวมือถือ 5G ชิป หน้าจอ กล้อง แบตเตอรี่ -เคส -ซ่อม",
            "Android smartphone long term review battery camera performance -case -repair -microphone -accessory",
            "smartphone review display chipset battery camera -case -repair -mic -flashlight",
            "iPhone review camera battery performance -case -repair -accessory",
        ),
    ),
    _leaf(
        "camera",
        "Camera",
        "กล้อง",
        "electronics",
        ("camera", "lens", "photography", "กล้อง", "เลนส์", "ถ่ายภาพ"),
        (
            "รีวิวกล้อง mirrorless autofocus คุณภาพไฟล์ -ไมค์ -สายคล้อง -กระเป๋า",
            "รีวิวกล้อง DSLR เซนเซอร์ autofocus -ไมค์ -โทรศัพท์",
            "รีวิวเลนส์กล้อง sharpness autofocus -สายคล้อง -กระเป๋า",
            "รีวิวกล้องถ่ายรูป หลังใช้งาน โฟกัส เซนเซอร์ คุณภาพไฟล์ -มือถือ -กระเป๋า",
            "เปรียบเทียบกล้อง mirrorless autofocus สี ภาพ วิดีโอ -มือถือ -ไมโครโฟน",
            "ทดสอบกล้อง เลนส์ โฟกัส ภาพถ่าย วิดีโอ รีวิว -มือถือ -สายคล้อง",
            "mirrorless camera review autofocus image quality -phone -microphone -strap -bag",
            "camera lens review sharpness autofocus photography -phone -strap -bag",
            "DSLR camera long term review image quality -phone -microphone -windscreen",
        ),
    ),
    _leaf(
        "laptop",
        "Laptop",
        "แล็ปท็อป",
        "electronics",
        ("laptop", "notebook", "แล็ปท็อป", "โน้ตบุ๊ก"),
        (
            "รีวิวโน้ตบุ๊ก หลังใช้งาน แบตเตอรี่ หน้าจอ ประสิทธิภาพ -กระเป๋า -มินิพีซี",
            "รีวิวโน้ตบุ๊กเกมมิ่ง ประสิทธิภาพ ความร้อน แบตเตอรี่ -กระเป๋า",
            "รีวิว MacBook หลังใช้งาน แบตเตอรี่ หน้าจอ -กระเป๋า",
            "รีวิวแล็ปท็อป หลังใช้งาน แบตเตอรี่ หน้าจอ ประสิทธิภาพ ความร้อน -กระเป๋า",
            "ทดสอบโน้ตบุ๊ก ทำงาน เล่นเกม ซีพียู แบตเตอรี่ หน้าจอ -กระเป๋า",
            "เปรียบเทียบแล็ปท็อป รีวิว ข้อดีข้อเสีย น้ำหนัก แบตเตอรี่ -กระเป๋า",
            "laptop long term review battery display keyboard -backpack -bag -mini pc -desktop",
            "gaming laptop review performance thermals battery -backpack -mini pc -desktop",
            "notebook review benchmark battery screen keyboard -bag -accessory -mini pc",
        ),
    ),
    _leaf(
        "audio",
        "Audio",
        "อุปกรณ์เสียง",
        "electronics",
        ("audio", "speaker", "microphone", "sound", "ลำโพง", "ไมโครโฟน", "เครื่องเสียง"),
        ("รีวิวลำโพง", "รีวิวไมโครโฟน", "audio gear review"),
    ),
    _leaf(
        "headphone",
        "Headphone",
        "หูฟัง",
        "electronics",
        ("headphone", "headset", "earbud", "earbuds", "หูฟัง", "เฮดเซต"),
        ("รีวิวหูฟัง", "รีวิว earbuds", "headphone review"),
    ),
    _leaf(
        "hardware",
        "Hardware",
        "ฮาร์ดแวร์คอมพิวเตอร์",
        "electronics",
        ("hardware", "cpu", "gpu", "ram", "mainboard", "pc", "การ์ดจอ", "ซีพียู", "คอมพิวเตอร์"),
        ("รีวิวฮาร์ดแวร์คอม", "รีวิวการ์ดจอ", "computer hardware review"),
    ),
    TaxonomyNodeDefinition("food_beverage", "Food & Beverage", "อาหารและเครื่องดื่ม", 1),
    TaxonomyNodeDefinition("food", "Food", "อาหาร", 2, "food_beverage"),
    _leaf(
        "general_food",
        "Food",
        "อาหาร",
        "food",
        ("food", "meal", "restaurant", "recipe", "อาหาร", "ร้านอาหาร", "เมนู", "ทำอาหาร"),
        ("รีวิวอาหาร", "รีวิวร้านอาหาร", "food review"),
    ),
    TaxonomyNodeDefinition("beverage", "Beverage", "เครื่องดื่ม", 2, "food_beverage"),
    _leaf(
        "drink",
        "Drink",
        "เครื่องดื่ม",
        "beverage",
        ("drink", "beverage", "coffee", "tea", "เครื่องดื่ม", "กาแฟ", "ชา"),
        ("รีวิวเครื่องดื่ม", "รีวิวกาแฟ", "drink review"),
    ),
    TaxonomyNodeDefinition("beauty", "Beauty & Personal Care", "ความงามและการดูแลตัวเอง", 1),
    TaxonomyNodeDefinition("personal_care", "Personal Care", "การดูแลและความงาม", 2, "beauty"),
    _leaf(
        "makeup",
        "Makeup",
        "เครื่องสำอาง",
        "personal_care",
        ("makeup", "cosmetic", "lipstick", "foundation", "แต่งหน้า", "เครื่องสำอาง", "ลิปสติก"),
        ("รีวิวเครื่องสำอาง", "สอนแต่งหน้า", "makeup review"),
    ),
    _leaf(
        "grooming",
        "Grooming",
        "การดูแลบุคลิกภาพ",
        "personal_care",
        ("grooming", "shaving", "hair care", "personal care", "โกนหนวด", "ดูแลผม", "ดูแลตัวเอง"),
        ("รีวิวอุปกรณ์ดูแลตัวเอง", "รีวิวเครื่องโกนหนวด", "grooming review"),
    ),
    TaxonomyNodeDefinition("fashion", "Fashion", "แฟชั่น", 1),
    TaxonomyNodeDefinition("clothing", "Clothing", "เสื้อผ้าและรองเท้า", 2, "fashion"),
    _leaf(
        "shirt",
        "Shirt",
        "เสื้อ",
        "clothing",
        ("shirt", "t-shirt", "top", "เสื้อ", "เสื้อเชิ้ต", "เสื้อยืด"),
        ("รีวิวเสื้อ", "แฟชั่นเสื้อ", "shirt review"),
    ),
    _leaf(
        "shoes",
        "Shoes",
        "รองเท้า",
        "clothing",
        ("shoes", "sneaker", "footwear", "รองเท้า", "สนีกเกอร์"),
        ("รีวิวรองเท้า", "รีวิวสนีกเกอร์", "shoes review"),
    ),
    TaxonomyNodeDefinition(
        "unknown",
        "Unknown/Other",
        "ไม่ทราบประเภท/อื่น ๆ",
        1,
        is_leaf=True,
    ),
)

_NODE_BY_KEY = {node.key: node for node in TAXONOMY_NODES}
ACTIVE_LEAF_KEYS = tuple(
    node.key for node in TAXONOMY_NODES if node.is_leaf and node.is_trainable
)

_LEAF_ALIASES = {
    "smartphone": "phone",
    "mobile": "phone",
    "mobile_phone": "phone",
    "phone": "phone",
    "camera": "camera",
    "laptop": "laptop",
    "notebook": "laptop",
    "audio": "audio",
    "headphones": "headphone",
    "headphone": "headphone",
    "hardware": "hardware",
    "food": "general_food",
    "food_drink": "general_food",
    "general_food": "general_food",
    "drink": "drink",
    "makeup": "makeup",
    "grooming": "grooming",
    "shirt": "shirt",
    "shoe": "shoes",
    "shoes": "shoes",
    "unknown": UNKNOWN_LEAF_KEY,
    "other": UNKNOWN_LEAF_KEY,
    "general": UNKNOWN_LEAF_KEY,
}


def active_leaf_definitions() -> tuple[TaxonomyNodeDefinition, ...]:
    return tuple(_NODE_BY_KEY[key] for key in ACTIVE_LEAF_KEYS)


def collection_queries_for_leaf(leaf_key: str) -> tuple[str, ...]:
    definition = _NODE_BY_KEY.get(normalize_taxonomy_leaf(leaf_key))
    if definition is None or not definition.is_trainable:
        return ()
    return definition.collection_queries


def taxonomy_profile_terms(leaf_key: str) -> list[str]:
    definition = _NODE_BY_KEY.get(normalize_taxonomy_leaf(leaf_key))
    if definition is None or not definition.is_trainable:
        return []
    path = taxonomy_path(definition.key)
    values = [
        path.get("category_level_1"),
        path.get("category_level_2"),
        path.get("category_level_3"),
        *definition.profile_terms,
    ]
    return list(dict.fromkeys(str(item).strip().lower() for item in values if item))


def normalize_taxonomy_leaf(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("&", "and")
    normalized = "_".join(normalized.replace("-", " ").split())
    return _LEAF_ALIASES.get(normalized, UNKNOWN_LEAF_KEY)


def taxonomy_path(leaf_key: str | None) -> Dict[str, str | bool | None]:
    key = normalize_taxonomy_leaf(leaf_key)
    leaf = _NODE_BY_KEY.get(key, _NODE_BY_KEY[UNKNOWN_LEAF_KEY])
    path: Dict[int, str] = {}
    current: TaxonomyNodeDefinition | None = leaf
    while current is not None:
        path[current.level] = current.name
        current = _NODE_BY_KEY.get(current.parent_key) if current.parent_key else None
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_leaf_key": leaf.key,
        "category_level_1": path.get(1),
        "category_level_2": path.get(2),
        "category_level_3": path.get(3),
        "is_unknown": leaf.key == UNKNOWN_LEAF_KEY,
    }


def _mapping_rule(node: TaxonomyNodeDefinition) -> str | None:
    if not node.is_trainable:
        return None
    return (
        "discovery_queries="
        + "|".join(node.collection_queries)
        + ";final_label=human_review"
    )


def sync_taxonomy_registry(db: Session) -> Dict[str, int]:
    created = 0
    updated = 0
    old_nodes_deactivated = (
        db.query(TaxonomyNode)
        .filter(
            TaxonomyNode.taxonomy_version != TAXONOMY_VERSION,
            TaxonomyNode.is_trainable.is_(True),
            TaxonomyNode.is_active.is_(True),
        )
        .update({TaxonomyNode.is_active: False}, synchronize_session=False)
    )
    verified_counts = {
        str(key): int(count) for key, count in _verified_coverage_query(db).all()
    }
    for definition in TAXONOMY_NODES:
        row = (
            db.query(TaxonomyNode)
            .filter(
                TaxonomyNode.taxonomy_version == TAXONOMY_VERSION,
                TaxonomyNode.node_key == definition.key,
            )
            .first()
        )
        leaf_is_ready = (
            definition.is_trainable
            and verified_counts.get(definition.key, 0) >= definition.minimum_sample_count
        )
        values = {
            "display_name": definition.name,
            "display_name_th": definition.name_th,
            "level": definition.level,
            "parent_key": definition.parent_key,
            "is_leaf": definition.is_leaf,
            "is_active": leaf_is_ready if definition.is_trainable else True,
            "is_trainable": definition.is_trainable,
            "minimum_sample_count": definition.minimum_sample_count,
            "source_dataset": YOUTUBE_PUBLIC_DATASET_SOURCE if definition.is_trainable else None,
            "source_category": "human_review" if definition.is_trainable else None,
            "source_subcategory": ",".join(definition.collection_queries) or None,
            "mapping_rule": _mapping_rule(definition),
        }
        if row is None:
            db.add(
                TaxonomyNode(
                    taxonomy_version=TAXONOMY_VERSION,
                    node_key=definition.key,
                    **values,
                )
            )
            created += 1
        else:
            for field, value in values.items():
                setattr(row, field, value)
            updated += 1

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "old_nodes_deactivated": int(old_nodes_deactivated or 0),
    }


def _verified_coverage_query(db: Session):
    from app.services.dataset_eligibility import production_transcript_conditions

    return (
        db.query(
            DatasetContent.taxonomy_leaf_key,
            func.count(DatasetContent.dataset_id),
        )
        .filter(*production_transcript_conditions())
        .group_by(DatasetContent.taxonomy_leaf_key)
    )


def taxonomy_coverage(db: Session) -> Dict[str, object]:
    counts = {str(key): int(count) for key, count in _verified_coverage_query(db).all()}
    leaves = []
    for definition in active_leaf_definitions():
        sample_count = counts.get(definition.key, 0)
        path = taxonomy_path(definition.key)
        leaves.append(
            {
                "leaf_key": definition.key,
                "category_level_1": path["category_level_1"],
                "category_level_2": path["category_level_2"],
                "category_level_3": path["category_level_3"],
                "source_dataset": YOUTUBE_PUBLIC_DATASET_SOURCE,
                "source_category": "human_review",
                "source_subcategories": list(definition.collection_queries),
                "minimum_sample_count": definition.minimum_sample_count,
                "verified_sample_count": sample_count,
                "ready": sample_count >= definition.minimum_sample_count,
            }
        )
    ready_count = sum(1 for item in leaves if item["ready"])
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "source_dataset": YOUTUBE_PUBLIC_DATASET_SOURCE,
        "minimum_samples_per_leaf": MIN_VERIFIED_SAMPLES,
        "leaf_count": len(leaves),
        "ready_leaf_count": ready_count,
        "ready": ready_count == len(leaves),
        "unknown_leaf_key": UNKNOWN_LEAF_KEY,
        "leaves": leaves,
    }


def ready_leaf_keys(db: Session) -> set[str]:
    coverage = taxonomy_coverage(db)
    return {
        str(item["leaf_key"])
        for item in coverage["leaves"]
        if bool(item["ready"])
    }


def serialize_taxonomy_nodes(rows: list[TaxonomyNode]) -> list[Dict[str, object]]:
    return [
        {
            "node_key": row.node_key,
            "display_name": row.display_name,
            "display_name_th": row.display_name_th,
            "level": int(row.level),
            "parent_key": row.parent_key,
            "is_leaf": bool(row.is_leaf),
            "is_active": bool(row.is_active),
            "is_trainable": bool(row.is_trainable),
            "minimum_sample_count": int(row.minimum_sample_count or 0),
        }
        for row in rows
    ]
