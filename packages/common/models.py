from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    plan = Column(String, default="starter")
    billing_status = Column(String, default="trial")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, default="active")

class Channel(Base):
    __tablename__ = "channels"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    type = Column(String)
    mode = Column(String)
    status = Column(String)
    credentials = Column(JSONB)
    phone_number = Column(String)

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    wa_id = Column(String)
    phone = Column(String)
    name = Column(String)
    attributes = Column(JSONB, default=dict)
    tags = Column(ARRAY(String), default=list)
    consent = Column(String)
    locale = Column(String)
    timezone = Column(String)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    contact_id = Column(ForeignKey("contacts.id"))
    channel_id = Column(ForeignKey("channels.id"))
    state = Column(String)
    assignee = Column(String)
    last_activity_at = Column(DateTime)

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id"))
    direction = Column(String)  # in|out
    type = Column(String)       # text|media|template
    content = Column(JSONB)
    template_id = Column(String, nullable=True)
    status = Column(String)     # delivered|read|failed
    meta = Column(JSONB)
    client_id = Column(String)
    created_at = Column(DateTime)

class Template(Base):
    __tablename__ = "templates"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    language = Column(String)
    category = Column(String)
    body = Column(Text)
    variables = Column(JSONB)
    status = Column(String)

class Flow(Base):
    __tablename__ = "flows"
    id = Column(String, primary_key=True)
    org_id = Column(ForeignKey("organizations.id"))
    name = Column(String)
    version = Column(Integer)
    graph = Column(JSONB)
    status = Column(String)
    created_by = Column(String)
# Modelos comunes
