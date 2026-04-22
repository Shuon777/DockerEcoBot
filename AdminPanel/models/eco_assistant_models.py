"""
ORM-модели для схемы eco_assistant.

Этот модуль содержит определения классов SQLAlchemy для таблиц в схеме eco_assistant.
Используется для работы с основными сущностями системы: объекты, ресурсы, модальности,
библиографические данные и связи между ними.

Все таблицы находятся в схеме 'eco_assistant'. Для использования с асинхронным движком
из database.py импортируйте Base отсюда или используйте свой собственный Base.
"""

import geoalchemy2
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, Date, DateTime, Table, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import JSONB

# Определяем свой Base для моделей схемы eco_assistant.
# Может быть заменён на Base из database.py при необходимости.
Base = declarative_base()

# ============================================================================
# 1. СПРАВОЧНИК ТИПОВ ОБЪЕКТОВ
# ============================================================================

class ObjectType(Base):
    """
    Справочник типов объектов.

    Определяет категории объектов (например, 'Объект флоры и фауны',
    'Географический объект', 'Услуга', 'Экспонат'). Каждый тип может иметь
    JSON-схему для описания допустимых свойств объектов этого типа.
    """
    __tablename__ = 'object_type'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор типа объекта')
    name = Column(String, unique=True, nullable=False, doc='Наименование типа объекта (уникальное)')
    schema = Column(JSONB, default={}, doc='JSON-схема, описывающая структуру свойств объектов данного типа')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    objects = relationship('Object', back_populates='object_type', cascade='all, delete-orphan')


# ============================================================================
# 2. ОСНОВНАЯ ТАБЛИЦА ОБЪЕКТОВ
# ============================================================================

class Object(Base):
    """
    Объект.

    Центральная сущность, представляющая реальный объект (вид флоры/фауны,
    географический объект, услугу и т.д.). Содержит уникальный db_id,
    ссылку на тип объекта и произвольные свойства в формате JSON.
    """
    __tablename__ = 'object'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор объекта')
    db_id = Column(String, unique=True, nullable=False, doc='Внешний идентификатор объекта (уникальный)')
    object_type_id = Column(Integer, ForeignKey('eco_assistant.object_type.id'), nullable=False, doc='Ссылка на тип объекта')
    object_properties = Column(JSONB, default={}, doc='JSON-объект с произвольными свойствами объекта')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    object_type = relationship('ObjectType', back_populates='objects')
    synonyms = relationship('ObjectNameSynonym', secondary='eco_assistant.object_name_synonym_link', back_populates='objects')
    related_objects = relationship('ObjectObjectLink', foreign_keys='ObjectObjectLink.object_id', back_populates='object')
    resources = relationship('Resource', secondary='eco_assistant.resource_object', back_populates='objects')


# ============================================================================
# 3. СИНОНИМЫ НАЗВАНИЙ ОБЪЕКТОВ
# ============================================================================

class ObjectNameSynonym(Base):
    """
    Справочник синонимов названий объектов.

    Хранит альтернативные названия (синонимы) объектов на разных языках.
    Позволяет осуществлять поиск объектов по различным вариантам написания.
    """
    __tablename__ = 'object_name_synonym'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор синонима')
    synonym = Column(String, nullable=False, doc='Текст синонима (альтернативное название)')
    language = Column(String(10), default='ru', doc='Код языка синонима (ru, en, латынь и т.д.)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')

    # Связи
    objects = relationship('Object', secondary='eco_assistant.object_name_synonym_link', back_populates='synonyms')


# Ассоциативная таблица для связи объектов и синонимов (многие-ко-многим)
object_name_synonym_link = Table(
    'object_name_synonym_link', Base.metadata,
    Column('object_id', Integer, ForeignKey('eco_assistant.object.id'), primary_key=True, doc='Идентификатор объекта'),
    Column('synonym_id', Integer, ForeignKey('eco_assistant.object_name_synonym.id'), primary_key=True, doc='Идентификатор синонима'),
    schema='eco_assistant'
)


# ============================================================================
# 4. СВЯЗИ МЕЖДУ ОБЪЕКТАМИ
# ============================================================================

class ObjectObjectLink(Base):
    """
    Связи между объектами.

    Позволяет устанавливать произвольные отношения между объектами
    (например, 'входит в состав', 'является частью', 'взаимодействует с').
    """
    __tablename__ = 'object_object_link'
    __table_args__ = {'schema': 'eco_assistant'}
    
    object_id = Column(Integer, ForeignKey('eco_assistant.object.id'), primary_key=True, doc='Идентификатор исходного объекта')
    related_object_id = Column(Integer, ForeignKey('eco_assistant.object.id'), primary_key=True, doc='Идентификатор связанного объекта')
    relation_type = Column(String, primary_key=True, doc='Тип отношения (например, "часть-целое", "симбиоз")')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания связи')

    # Связи
    object = relationship('Object', foreign_keys=[object_id], back_populates='related_objects')
    related_object = relationship('Object', foreign_keys=[related_object_id])


# ============================================================================
# 5. СПРАВОЧНИК МОДАЛЬНОСТЕЙ
# ============================================================================

class Modality(Base):
    """
    Справочник модальностей ресурсов.

    Определяет типы модальностей, которые могут быть у ресурса: текст, изображение,
    геоданные и т.д. Каждая модальность ссылается на таблицу, в которой хранятся
    конкретные значения этого типа.
    """
    __tablename__ = 'modality'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор модальности')
    modality_type = Column(String, unique=True, nullable=False, doc='Тип модальности (например, "Текст", "Изображение", "Геоданные")')
    value_table_name = Column(String, nullable=False, doc='Имя таблицы, в которой хранятся значения данной модальности')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    resource_values = relationship('ResourceValue', back_populates='modality')


# ============================================================================
# 6. ТАБЛИЦЫ ЗНАЧЕНИЙ МОДАЛЬНОСТЕЙ
# ============================================================================

class TextValue(Base):
    """
    Значения текстовой модальности.

    Хранит структурированные текстовые данные (например, описания, статьи, заметки)
    в формате JSON. Каждая запись соответствует одному текстовому ресурсу.
    """
    __tablename__ = 'text_value'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор текстового значения')
    structured_data = Column(JSONB, nullable=False, doc='Структурированные текстовые данные в формате JSON')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')


class ImageValue(Base):
    """
    Значения модальности "Изображение".

    Содержит информацию об изображениях: URL, путь к файлу, формат.
    Хотя бы одно из полей url или file_path должно быть заполнено.
    """
    __tablename__ = 'image_value'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор изображения')
    url = Column(String, doc='URL изображения в интернете')
    file_path = Column(String, doc='Путь к файлу изображения в локальной файловой системе')
    format = Column(String(20), doc='Формат изображения (jpg, png, gif и т.д.)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')


class GeodataValue(Base):
    """
    Значения модальности "Геоданные".

    Хранит геометрические объекты (точки, линии, полигоны) в формате PostGIS.
    Используется для представления географических локаций на карте.
    """
    __tablename__ = 'geodata_value'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор геоданных')
    geometry = Column(geoalchemy2.Geometry(geometry_type='GEOMETRY', srid=4326), nullable=False, doc='Геометрический объект в системе координат WGS84')
    geometry_type = Column(String, doc='Тип геометрии (Point, LineString, Polygon и т.д.)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')


# ============================================================================
# 7. СВЯЗЬ РЕСУРСОВ СО ЗНАЧЕНИЯМИ МОДАЛЬНОСТЕЙ
# ============================================================================

class ResourceValue(Base):
    """
    Связь ресурса с модальностью и значением.

    Соединяет ресурс с конкретным значением модальности (текст, изображение, геоданные).
    Один ресурс может иметь несколько модальностей, но только одну запись каждого типа.
    """
    __tablename__ = 'resource_value'
    __table_args__ = (
        UniqueConstraint('resource_id', 'modality_id', name='uq_resource_modality'),
        {'schema': 'eco_assistant'}
    )
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор связи')
    resource_id = Column(Integer, ForeignKey('eco_assistant.resource.id'), nullable=False, doc='Ссылка на ресурс')
    modality_id = Column(Integer, ForeignKey('eco_assistant.modality.id'), nullable=False, doc='Ссылка на тип модальности')
    value_id = Column(Integer, doc='Идентификатор значения в соответствующей таблице (text_value, image_value, geodata_value)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания связи')

    # Связи
    resource = relationship('Resource', back_populates='resource_values')
    modality = relationship('Modality', back_populates='resource_values')


# ============================================================================
# 8. СПРАВОЧНИКИ ДЛЯ БИБЛИОГРАФИЧЕСКИХ ДАННЫХ
# ============================================================================

class Author(Base):
    """
    Справочник авторов.

    Содержит имена авторов, которые могут быть указаны в библиографических данных ресурса.
    """
    __tablename__ = 'author'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор автора')
    name = Column(String, unique=True, nullable=False, doc='ФИО автора (уникальное)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')


class Source(Base):
    """
    Справочник источников.

    Содержит названия источников (книги, статьи, веб-сайты), из которых получена информация.
    """
    __tablename__ = 'source'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор источника')
    name = Column(String, unique=True, nullable=False, doc='Название источника (уникальное)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')


class ReliabilityLevel(Base):
    """
    Справочник уровней достоверности.

    Определяет градации достоверности информации (например, 'высокая', 'средняя', 'низкая').
    """
    __tablename__ = 'reliability_level'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор уровня достоверности')
    name = Column(String, unique=True, nullable=False, doc='Наименование уровня достоверности (уникальное)')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')


# ============================================================================
# 9. БИБЛИОГРАФИЧЕСКИЕ ДАННЫЕ
# ============================================================================

class Bibliographic(Base):
    """
    Библиографические данные.

    Объединяет информацию об авторе, дате, источнике и уровне достоверности.
    Используется как часть статических метаданных ресурса.
    """
    __tablename__ = 'bibliographic'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор библиографической записи')
    author_id = Column(Integer, ForeignKey('eco_assistant.author.id'), doc='Ссылка на автора')
    date = Column(Date, doc='Дата публикации или создания материала')
    source_id = Column(Integer, ForeignKey('eco_assistant.source.id'), doc='Ссылка на источник')
    reliability_level_id = Column(Integer, ForeignKey('eco_assistant.reliability_level.id'), doc='Ссылка на уровень достоверности')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    author = relationship('Author', backref='bibliographic_records')
    source = relationship('Source', backref='bibliographic_records')
    reliability_level = relationship('ReliabilityLevel', backref='bibliographic_records')
    resource_statics = relationship('ResourceStatic', back_populates='bibliographic')


# ============================================================================
# 10. ДАННЫЕ О СОЗДАНИИ
# ============================================================================

class Creation(Base):
    """
    Данные о создании (источник).

    Описывает, как и с помощью каких инструментов был создан ресурс
    (например, 'ручной ввод', 'автоматический парсинг', 'импорт из Excel').
    """
    __tablename__ = 'creation'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор записи о создании')
    creation_type = Column(String, doc='Тип создания (ручной, автоматический и т.д.)')
    creation_tool = Column(String, doc='Инструмент, использованный для создания')
    creation_params = Column(JSONB, doc='Параметры создания в формате JSON')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    resource_statics = relationship('ResourceStatic', back_populates='creation')


# ============================================================================
# 11. СТАТИЧЕСКИЕ МЕТАДАННЫЕ РЕСУРСА
# ============================================================================

class ResourceStatic(Base):
    """
    Статические метаданные ресурса.

    Объединяет библиографические данные и данные о создании, образуя неизменяемую часть
    метаданных ресурса. Позволяет повторно использовать одни и те же статические данные
    для нескольких ресурсов.
    """
    __tablename__ = 'resource_static'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор статических метаданных')
    static_id = Column(String, unique=True, doc='Внешний идентификатор статических метаданных (опциональный)')
    bibliographic_id = Column(Integer, ForeignKey('eco_assistant.bibliographic.id'), nullable=False, doc='Ссылка на библиографические данные')
    creation_id = Column(Integer, ForeignKey('eco_assistant.creation.id'), nullable=False, doc='Ссылка на данные о создании')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    bibliographic = relationship('Bibliographic', back_populates='resource_statics')
    creation = relationship('Creation', back_populates='resource_statics')
    resources = relationship('Resource', back_populates='resource_static')


# ============================================================================
# 12. МЕТАДАННЫЕ СОПРОВОЖДЕНИЯ
# ============================================================================

class SupportMetadata(Base):
    """
    Метаданные сопровождения.

    Содержит параметры, которые могут изменяться в процессе жизненного цикла ресурса
    (например, флаги обработки, хэши, служебная информация). Хранятся в формате JSON.
    """
    __tablename__ = 'support_metadata'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор метаданных сопровождения')
    parameters = Column(JSONB, nullable=False, doc='Параметры сопровождения в формате JSON')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    resources = relationship('Resource', back_populates='support_metadata')


# ============================================================================
# 13. РЕСУРС (ЦЕНТРАЛЬНАЯ СУЩНОСТЬ)
# ============================================================================

class Resource(Base):
    """
    Ресурс.

    Основная сущность, представляющая информационный ресурс (статья, изображение,
    карта и т.д.). Содержит заголовок, URI, признаки (features), ссылки на статические
    метаданные и метаданные сопровождения. Ресурс может быть связан с несколькими
    объектами и иметь несколько модальностей.
    """
    __tablename__ = 'resource'
    __table_args__ = {'schema': 'eco_assistant'}
    
    id = Column(Integer, primary_key=True, doc='Уникальный идентификатор ресурса')
    title = Column(String, doc='Заголовок ресурса')
    uri = Column(String, doc='URI ресурса (например, URL или внутренний идентификатор)')
    features = Column(JSONB, doc='Признаки ресурса в формате JSON (онтология: сезон, место и т.д.)')
    text_id = Column(String, unique=True, doc='Уникальный текстовый идентификатор ресурса (используется для связи с внешними системами)')
    resource_static_id = Column(Integer, ForeignKey('eco_assistant.resource_static.id'), nullable=False, doc='Ссылка на статические метаданные')
    support_metadata_id = Column(Integer, ForeignKey('eco_assistant.support_metadata.id'), nullable=False, doc='Ссылка на метаданные сопровождения')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания записи')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), doc='Дата и время последнего обновления записи')

    # Связи
    resource_static = relationship('ResourceStatic', back_populates='resources')
    support_metadata = relationship('SupportMetadata', back_populates='resources')
    objects = relationship('Object', secondary='eco_assistant.resource_object', back_populates='resources')
    resource_values = relationship('ResourceValue', back_populates='resource')
    related_resources = relationship('ResourceResourceLink', foreign_keys='ResourceResourceLink.resource_id', back_populates='resource')


# ============================================================================
# 14. СВЯЗЬ РЕСУРСА С ОБЪЕКТАМИ
# ============================================================================

# Ассоциативная таблица для связи ресурсов и объектов (многие-ко-многим)
resource_object_table = Table(
    'resource_object', Base.metadata,
    Column('resource_id', Integer, ForeignKey('eco_assistant.resource.id'), primary_key=True, doc='Идентификатор ресурса'),
    Column('object_id', Integer, ForeignKey('eco_assistant.object.id'), primary_key=True, doc='Идентификатор объекта'),
    Column('relation_type', String, doc='Тип отношения между ресурсом и объектом'),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания связи'),
    schema='eco_assistant'
)


# ============================================================================
# 15. СВЯЗЬ РЕСУРСА С РЕСУРСАМИ
# ============================================================================

class ResourceResourceLink(Base):
    """
    Связи между ресурсами.

    Позволяет устанавливать произвольные отношения между ресурсами
    (например, 'является частью', 'ссылается на', 'дублирует').
    """
    __tablename__ = 'resource_resource_link'
    __table_args__ = {'schema': 'eco_assistant'}
    
    resource_id = Column(Integer, ForeignKey('eco_assistant.resource.id'), primary_key=True, doc='Идентификатор исходного ресурса')
    related_resource_id = Column(Integer, ForeignKey('eco_assistant.resource.id'), primary_key=True, doc='Идентификатор связанного ресурса')
    relation_type = Column(String, primary_key=True, doc='Тип отношения между ресурсами')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), doc='Дата и время создания связи')

    # Связи
    resource = relationship('Resource', foreign_keys=[resource_id], back_populates='related_resources')
    related_resource = relationship('Resource', foreign_keys=[related_resource_id])


# ============================================================================
# КОНЕЦ ОПРЕДЕЛЕНИЙ
# ============================================================================